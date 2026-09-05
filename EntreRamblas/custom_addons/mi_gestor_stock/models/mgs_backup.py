# -*- coding: utf-8 -*-
"""Persistencia en disco: un archivo con TODO el programa dentro.

Odoo guarda los datos en PostgreSQL (no puede funcionar sobre un fichero
suelto tipo SQLite: usa vistas, secuencias y tipos propios de Postgres). Lo
que sí se puede es volcar el estado completo a un único archivo del disco de
forma automática, y eso es lo que hace este modelo:

    mi_base_stock-ultima.zip
      |- dump.sql       -> la base de datos entera (productos, stock, ventas,
      |                    usuarios, configuración de los dispositivos...)
      |- filestore/     -> imágenes y adjuntos
      |- manifest.json  -> versión de Odoo y módulos instalados

Ese .zip es el formato de copia NATIVO de Odoo: sirve para restaurar en este
equipo (restore-backup.ps1) o en cualquier otro con Odoo 18.

⚠️ Gotcha: `odoo.service.db.dump_db()` lleva el decorador
`check_db_management_enabled`, que lanza AccessDenied cuando `list_db = False`
—y en odoo.conf está a False a propósito, para que nadie vea el gestor de
bases de datos desde el navegador—. Por eso aquí se reconstruye el volcado
(pg_dump + filestore + manifest + zip), que es exactamente lo que hace Odoo
por dentro, sin depender de esa opción.
"""
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta

import odoo
import odoo.release
from odoo import api, fields, models, _
from odoo.tools.misc import exec_pg_environ, find_pg_tool
from odoo.tools.osutil import zip_dir

_logger = logging.getLogger(__name__)

# Sitios donde buscar pg_dump en Windows si no está en el PATH. Se puede
# evitar del todo poniendo `pg_path` en odoo.conf (ya viene puesto).
_PG_BIN_GLOBS = (
    r"C:\Program Files\PostgreSQL",
    r"C:\Program Files (x86)\PostgreSQL",
)


class MgsBackup(models.Model):
    _name = "mgs.backup"
    _description = "Copia de seguridad"
    _order = "date desc, id desc"

    name = fields.Char("Archivo", readonly=True)
    date = fields.Datetime("Fecha", readonly=True, default=fields.Datetime.now)
    path = fields.Char("Ruta completa", readonly=True)
    size = fields.Integer("Tamaño (bytes)", readonly=True)
    size_human = fields.Char("Tamaño", compute="_compute_size_human")
    kind = fields.Selection([
        ("auto", "Automática"),
        ("manual", "Manual"),
    ], string="Origen", default="auto", readonly=True)
    state = fields.Selection([
        ("done", "Correcta"),
        ("error", "Con error"),
    ], string="Estado", default="done", readonly=True)
    message = fields.Text("Detalle", readonly=True)

    @api.depends("size")
    def _compute_size_human(self):
        for backup in self:
            size = float(backup.size or 0)
            for unit in ("B", "KB", "MB", "GB"):
                if size < 1024 or unit == "GB":
                    backup.size_human = "%.1f %s" % (size, unit)
                    break
                size /= 1024

    # ------------------------------------------------------------------
    # Rutas
    # ------------------------------------------------------------------
    @api.model
    def _mgs_default_dir(self):
        """Carpeta por defecto: <data_dir>/backups, junto al filestore.

        `data_dir` sale de odoo.conf (aquí, EntreRamblas\\.odoo_data) y Odoo lo
        normaliza a ruta absoluta al arrancar. Para dejar las copias en el
        disco externo, basta con cambiar la carpeta en la pantalla de
        Configuración.
        """
        return os.path.join(odoo.tools.config["data_dir"], "backups")

    @api.model
    def _mgs_dir(self, config=None):
        config = config or self.env["mgs.config"]._mgs_get()
        directory = (config.backup_dir or "").strip() or self._mgs_default_dir()
        os.makedirs(directory, exist_ok=True)
        return directory

    @api.model
    def _mgs_latest_path(self, config=None):
        """El archivo permanente: siempre la última foto completa."""
        try:
            directory = self._mgs_dir(config)
        except OSError:
            directory = (config.backup_dir if config else "") or self._mgs_default_dir()
        return os.path.join(directory, "%s-ultima.zip" % self.env.cr.dbname)

    @api.model
    def _mgs_pg_tool(self, name):
        """pg_dump / psql, aunque PostgreSQL no esté en el PATH de Windows."""
        try:
            return find_pg_tool(name)
        except Exception:  # noqa: BLE001 - Odoo lanza Exception a secas
            for root in _PG_BIN_GLOBS:
                if not os.path.isdir(root):
                    continue
                for version in sorted(os.listdir(root), reverse=True):
                    candidate = os.path.join(root, version, "bin")
                    if os.path.isfile(os.path.join(candidate, name + ".exe")):
                        odoo.tools.config["pg_path"] = candidate
                        return find_pg_tool(name)
            raise

    # ------------------------------------------------------------------
    # Volcado
    # ------------------------------------------------------------------
    def _mgs_manifest(self):
        """Mismo manifest.json que genera Odoo, para que el .zip sea
        restaurable desde el gestor de bases de datos estándar."""
        cr = self.env.cr
        cr.execute("SELECT name, latest_version FROM ir_module_module WHERE state = 'installed'")
        return {
            "odoo_dump": "1",
            "db_name": cr.dbname,
            "version": odoo.release.version,
            "version_info": odoo.release.version_info,
            "major_version": odoo.release.major_version,
            "pg_version": "%d.%d" % divmod(cr._obj.connection.server_version / 100, 100),
            "modules": dict(cr.fetchall()),
        }

    def _mgs_write_zip(self, target):
        """Escribe el .zip completo en `target` (primero a un temporal)."""
        db_name = self.env.cr.dbname
        tmp_target = target + ".part"
        with tempfile.TemporaryDirectory() as dump_dir:
            filestore = odoo.tools.config.filestore(db_name)
            if os.path.exists(filestore):
                shutil.copytree(filestore, os.path.join(dump_dir, "filestore"))
            with open(os.path.join(dump_dir, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(self._mgs_manifest(), fh, indent=4)
            subprocess.run(
                [self._mgs_pg_tool("pg_dump"), "--no-owner",
                 "--file=" + os.path.join(dump_dir, "dump.sql"), db_name],
                env=exec_pg_environ(), stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT, check=True,
            )
            with open(tmp_target, "wb") as stream:
                # dump.sql el primero dentro del zip: es lo que espera el
                # restaurador de Odoo para no tener que leerlo entero.
                zip_dir(dump_dir, stream, include_dir=False,
                        fnct_sort=lambda name: name != "dump.sql")
        os.replace(tmp_target, target)
        return os.path.getsize(target)

    @api.model
    def _mgs_run_backup(self, kind="auto"):
        """Hace una copia y deja constancia (también si falla)."""
        config = self.env["mgs.config"]._mgs_get()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        name = "%s-%s.zip" % (self.env.cr.dbname, stamp.strftime("%Y%m%d-%H%M"))
        try:
            directory = self._mgs_dir(config)
            target = os.path.join(directory, name)
            size = self._mgs_write_zip(target)
            # Copia con nombre fijo: SIEMPRE el estado más reciente, para que
            # la tarea que sincroniza con el disco externo tenga una ruta
            # estable a la que apuntar.
            latest = self._mgs_latest_path(config)
            shutil.copyfile(target, latest + ".part")
            os.replace(latest + ".part", latest)
        except Exception as err:  # noqa: BLE001 - se registra, no tumba el cron
            _logger.exception("mi_gestor_stock: falló la copia de seguridad")
            return self.sudo().create({
                "name": name, "kind": kind, "state": "error",
                "message": str(err),
            })

        _logger.info("mi_gestor_stock: copia de seguridad en %s (%s bytes)", target, size)
        backup = self.sudo().create({
            "name": name, "path": target, "size": size, "kind": kind,
            "state": "done",
            "message": _("Copia completa (base de datos + adjuntos). "
                         "Archivo permanente: %s", latest),
        })
        config.sudo().write({
            "backup_last_date": fields.Datetime.now(),
            "backup_last_path": target,
        })
        self._mgs_purge(config)
        return backup

    @api.model
    def _mgs_purge(self, config=None):
        """Conserva solo las N copias con fecha más recientes."""
        config = config or self.env["mgs.config"]._mgs_get()
        keep = max(1, config.backup_keep or 14)
        old = self.sudo().search([("state", "=", "done")], order="date desc")[keep:]
        for backup in old:
            if backup.path and os.path.isfile(backup.path):
                try:
                    os.remove(backup.path)
                except OSError as err:
                    _logger.warning("mi_gestor_stock: no se pudo borrar %s (%s)",
                                    backup.path, err)
        # Los registros con error se quedan como aviso hasta que se resuelvan.
        old.unlink()

    # ------------------------------------------------------------------
    # Cron (data/mgs_hardware_data.xml)
    # ------------------------------------------------------------------
    @api.model
    def _mgs_cron_backup(self):
        """Se ejecuta cada hora y decide si toca copia.

        Mirar la última copia hecha (en vez de fiarlo todo al intervalo del
        cron) hace que el ritmo se respete aunque el equipo haya estado
        apagado: al encender la tienda por la mañana se hace la copia que
        tocaba, no cuatro seguidas.
        """
        config = self.env["mgs.config"]._mgs_get()
        if not config.backup_enabled:
            return False
        every = max(1, config.backup_every_hours or 6)
        last = self.sudo().search([("state", "=", "done")], order="date desc", limit=1)
        if last and last.date > fields.Datetime.now() - timedelta(hours=every):
            return False
        return self._mgs_run_backup(kind="auto")

    @api.model
    def action_mgs_backup_now(self):
        """Botón «Hacer copia ahora» de la lista de copias."""
        backup = self._mgs_run_backup(kind="manual")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if backup.state == "done" else "danger",
                "message": (_("Copia guardada en %s", backup.path)
                            if backup.state == "done"
                            else _("La copia ha fallado: %s", backup.message)),
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
