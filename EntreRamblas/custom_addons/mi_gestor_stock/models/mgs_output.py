# -*- coding: utf-8 -*-
"""Carpetas de salida para lo que genera el programa.

Todo lo que se guarda (informe mensual, CSV de estadísticas, factura, ticket)
lo escribe el propio servidor en una ubicación ADMINISTRADA, común a todo el
equipo: `%ProgramData%\\EntreRamblas\\Documentos`, con las subcarpetas
`Facturas`, `Informes` y `Tickets`. El servicio de Windows corre como
LocalService y no tiene perfil de usuario propio (ni Escritorio ni Documentos
fiables), de ahí que ya no sea una ruta elegible ni se intente abrir el
Explorador desde el servidor: el instalador crea el acceso directo del
Escritorio y los permisos (instalador/preparar-documentos.ps1).
`_mgs_save_output` sigue siendo el único punto de escritura.
"""
import filecmp
import logging
import os
import shutil
import subprocess

from odoo import api, fields, models
from odoo.exceptions import UserError

from .mgs_permissions import require_manager

_logger = logging.getLogger(__name__)

# Subcarpetas fijas dentro de la carpeta administrada. Así nunca se mezclan
# los documentos para consulta/gestoría, las facturas fiscales y los tickets.
SUBFOLDERS = {"informes": "Informes", "facturas": "Facturas", "tickets": "Tickets"}

# Espacio libre mínimo para poder guardar un documento con margen.
MIN_FREE_BYTES = 50 * 1024 * 1024

# Nombres que Windows reserva para dispositivos: no se pueden usar como archivo.
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *("COM%d" % n for n in range(1, 10)),
                   *("LPT%d" % n for n in range(1, 10))}


def managed_documents_dir():
    """Ubicación administrada de los documentos."""
    if os.name == "nt":
        root = os.environ.get("ProgramData") or r"C:\ProgramData"
    else:
        root = os.path.expanduser("~")
    return os.path.join(root, "EntreRamblas", "Documentos")


class MgsConfig(models.Model):
    _inherit = "mgs.config"

    output_dir = fields.Char(
        "Carpeta de documentos",
        default=lambda self: self._mgs_default_output_dir(),
        readonly=True,
        help="Ubicación administrada por el programa. Contiene las subcarpetas "
             "«Facturas», «Informes» y «Tickets». En el Escritorio hay un acceso "
             "directo llamado «Documentos Clavel y Azahar».")
    output_invoices_dir = fields.Char(
        "Carpeta de facturas", compute="_compute_output_directories", readonly=True)
    output_reports_dir = fields.Char(
        "Carpeta de informes", compute="_compute_output_directories", readonly=True)
    output_tickets_dir = fields.Char(
        "Carpeta de tickets", compute="_compute_output_directories", readonly=True)

    @api.model
    def _mgs_default_output_dir(self):
        return managed_documents_dir()

    def _mgs_base_dir(self):
        return (self.output_dir or "").strip() or self._mgs_default_output_dir()

    @api.depends("output_dir")
    def _compute_output_directories(self):
        """Muestra las rutas finales sin crear archivos al abrir Ajustes."""
        for config in self:
            base = config._mgs_base_dir()
            config.output_invoices_dir = os.path.join(base, SUBFOLDERS["facturas"])
            config.output_reports_dir = os.path.join(base, SUBFOLDERS["informes"])
            config.output_tickets_dir = os.path.join(base, SUBFOLDERS["tickets"])

    # ---- Validación --------------------------------------------------
    def _mgs_ensure_folder(self, directory):
        """Crea `directory` si falta y comprueba que es una carpeta escribible
        con espacio libre. Cualquier fallo sale como UserError en español."""
        env = self.env
        if os.path.exists(directory) and not os.path.isdir(directory):
            raise UserError(env._(
                "Hay un archivo donde debería haber una carpeta: %s. "
                "Renómbralo o muévelo y vuelve a comprobar.", directory))
        try:
            os.makedirs(directory, exist_ok=True)
        except PermissionError as err:
            raise UserError(env._(
                "El programa no tiene permiso para crear la carpeta %s (%s).",
                directory, err)) from err
        except OSError as err:
            raise UserError(env._(
                "No se ha podido preparar la carpeta %s: %s. Comprueba que el "
                "disco está disponible.", directory, err)) from err
        probe = os.path.join(directory, ".mgs-escritura-%d.tmp" % os.getpid())
        try:
            with open(probe, "wb") as handle:
                handle.write(b"ok")
            os.remove(probe)
        except PermissionError as err:
            raise UserError(env._(
                "El programa no tiene permiso de escritura en %s (%s).",
                directory, err)) from err
        except OSError as err:
            raise UserError(env._(
                "No se puede escribir en %s: %s.", directory, err)) from err
        try:
            free = shutil.disk_usage(directory).free
        except OSError as err:
            raise UserError(env._(
                "No se ha podido comprobar el espacio libre de %s: %s", directory, err)) from err
        if free < MIN_FREE_BYTES:
            raise UserError(env._(
                "Queda muy poco espacio libre en el disco de %s (%d MB).",
                directory, free // (1024 * 1024)))
        return directory

    def _mgs_output_dir(self, kind):
        """Ruta absoluta de la subcarpeta `kind` («informes», «facturas» o
        «tickets»), creándola y validándola."""
        self.ensure_one()
        if kind not in SUBFOLDERS:
            raise UserError(self.env._("Tipo de carpeta desconocido: %s", kind))
        base = self._mgs_base_dir()
        self._mgs_ensure_folder(base)
        return self._mgs_ensure_folder(os.path.join(base, SUBFOLDERS[kind]))

    def _mgs_check_filename(self, filename):
        name = os.path.basename((filename or "").replace("\\", "/"))
        stem = os.path.splitext(name)[0].rstrip(" .")
        if not name or name in (".", "..") or stem.upper() in _RESERVED_NAMES:
            raise UserError(self.env._(
                "«%s» no es un nombre de archivo válido en Windows.", filename))
        return name

    def _mgs_save_output(self, kind, filename, content):
        """Escribe `content` (bytes) en la carpeta de `kind` con `filename`.

        Si ese nombre ya existe se prueba con «-2», «-3»... en vez de
        sobrescribir: dos informes del mismo periodo generados en momentos
        distintos (una corrección, una segunda copia para la gestoría) tienen
        que quedar los dos, no que el segundo borre el primero.
        """
        self.ensure_one()
        filename = self._mgs_check_filename(filename)
        directory = self._mgs_output_dir(kind)
        base_name, ext = os.path.splitext(filename)
        path = os.path.join(directory, filename)
        counter = 2
        while True:
            try:
                # "xb": falla si el nombre ya existe, sin carrera entre
                # comprobar y crear.
                with open(path, "xb") as handle:
                    handle.write(content)
                return path
            except FileExistsError:
                path = os.path.join(directory, "%s-%d%s" % (base_name, counter, ext))
                counter += 1
            except PermissionError as err:
                raise UserError(self.env._(
                    "No hay permiso para guardar %s (%s).", path, err)) from err
            except OSError as err:
                raise UserError(self.env._(
                    "No se ha podido guardar %s: %s", path, err)) from err

    def action_mgs_check_output_folders(self):
        """Comprueba (y crea si faltan) las tres carpetas: existencia, tipo,
        escritura y espacio libre."""
        self.ensure_one()
        require_manager(self.env)
        invoices = self._mgs_output_dir("facturas")
        reports = self._mgs_output_dir("informes")
        tickets = self._mgs_output_dir("tickets")
        return self._mgs_notify(self.env._(
            "Carpetas correctas. Facturas: %s | Informes: %s | Tickets: %s",
            invoices, reports, tickets))

    # Nombre anterior, por si algo externo aún lo llama.
    action_mgs_prepare_output_folders = action_mgs_check_output_folders

    # ---- Migración desde rutas antiguas -----------------------------
    @api.model
    def _mgs_grant_documents_access(self, directory):
        """Mejor esfuerzo: LocalService escribe, los usuarios del equipo leen.
        El instalador ya lo hace con permisos de administrador; esto solo
        cubre una actualización, y un fallo aquí no es un error."""
        if os.name != "nt":
            return
        try:
            subprocess.run(
                ["icacls", directory, "/grant", "*S-1-5-19:(OI)(CI)M",
                 "*S-1-5-32-545:(OI)(CI)RX"],
                check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as err:
            _logger.warning("mi_gestor_stock: no se pudieron ajustar los permisos de %s: %s",
                            directory, err)

    @api.model
    def _mgs_copy_one(self, source, target_dir, name):
        """Copia `source`; devuelve False si ya hay una copia idéntica."""
        base_name, ext = os.path.splitext(name)
        target = os.path.join(target_dir, name)
        counter = 2
        while os.path.exists(target):
            if filecmp.cmp(source, target, shallow=False):
                return False
            target = os.path.join(target_dir, "%s-%d%s" % (base_name, counter, ext))
            counter += 1
        shutil.copy2(source, target)
        return True

    @api.model
    def _mgs_copy_legacy_documents(self, old_base, new_base):
        """Copia sin borrar nada los documentos de `old_base` a `new_base`.

        Nombres repetidos con contenido distinto → «-2», «-3»...; con el mismo
        contenido no se vuelve a copiar (la migración es idempotente).
        Devuelve cuántos archivos se han copiado."""
        old_base, new_base = os.path.abspath(old_base), os.path.abspath(new_base)
        if old_base == new_base or not os.path.isdir(old_base):
            return 0
        copied = 0
        for folder in SUBFOLDERS.values():
            source_dir = os.path.join(old_base, folder)
            if not os.path.isdir(source_dir):
                continue
            target_dir = os.path.join(new_base, folder)
            try:
                os.makedirs(target_dir, exist_ok=True)
                entries = os.listdir(source_dir)
            except OSError as err:
                _logger.warning("mi_gestor_stock: carpeta antigua inaccesible %s: %s",
                                source_dir, err)
                continue
            for entry in entries:
                source = os.path.join(source_dir, entry)
                if not os.path.isfile(source):
                    continue
                try:
                    if self._mgs_copy_one(source, target_dir, entry):
                        copied += 1
                except OSError as err:
                    _logger.warning("mi_gestor_stock: no se pudo copiar %s: %s", source, err)
        return copied

    @api.model
    def _mgs_migrate_documents_location(self):
        """Idempotente: fija la ubicación administrada, prepara las carpetas y
        copia los documentos de la ruta antigua (configurada o por defecto)."""
        config = self.sudo()._mgs_get()
        new_base = self._mgs_default_output_dir()
        old_candidates = [(config.output_dir or "").strip(),
                          os.path.join(os.path.expanduser("~"), "Documents", "Entre Ramblas")]
        if (config.output_dir or "").strip() != new_base:
            config.output_dir = new_base
        try:
            for folder in SUBFOLDERS.values():
                os.makedirs(os.path.join(new_base, folder), exist_ok=True)
        except OSError as err:
            _logger.warning("mi_gestor_stock: no se pudieron crear las carpetas en %s: %s",
                            new_base, err)
            return
        self._mgs_grant_documents_access(new_base)
        for old_base in dict.fromkeys(path for path in old_candidates if path):
            copied = self._mgs_copy_legacy_documents(old_base, new_base)
            if copied:
                _logger.info("mi_gestor_stock: %d documentos copiados de %s a %s",
                             copied, old_base, new_base)
