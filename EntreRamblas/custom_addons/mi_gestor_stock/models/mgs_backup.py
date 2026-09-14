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
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4
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
        ("close", "Cierre de caja"),
        ("pre-actualizacion", "Antes de actualizar"),
    ], string="Origen", default="auto", readonly=True)
    state = fields.Selection([
        ("done", "Correcta"),
        ("error", "Con error"),
    ], string="Estado", default="done", readonly=True)
    message = fields.Text("Detalle", readonly=True)
    checksum = fields.Char("SHA-256", readonly=True)
    replica_path = fields.Char("Archivo SSD", readonly=True)
    replica_state = fields.Selection([
        ("none", "SSD sin configurar"), ("done", "SSD correcto"),
        ("error", "SSD pendiente / error"),
    ], default="none", readonly=True)

    @api.model
    def _mgs_checksum(self, path):
        with open(path, "rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

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
            # El SQL y la lista de adjuntos comparten la misma instantánea.
            # Si un adjunto desaparece durante la copia, se rechaza la copia.
            with odoo.sql_db.db_connect(db_name).cursor() as snapshot:
                snapshot.execute("SELECT pg_export_snapshot()")
                snapshot_id = snapshot.fetchone()[0]
                snapshot.execute("SELECT DISTINCT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL")
                filenames = [row[0] for row in snapshot.fetchall()]
                snapshot_env = api.Environment(snapshot, self.env.uid, dict(self.env.context))
                with open(os.path.join(dump_dir, "manifest.json"), "w", encoding="utf-8") as fh:
                    json.dump(snapshot_env["mgs.backup"]._mgs_manifest(), fh, indent=4)
                subprocess.run(
                    [self._mgs_pg_tool("pg_dump"), "--no-owner", "--snapshot=" + snapshot_id,
                     "--file=" + os.path.join(dump_dir, "dump.sql"), db_name],
                    env=exec_pg_environ(), stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, check=True, timeout=1800,
                )
                filestore = Path(odoo.tools.config.filestore(db_name)).resolve()
                for filename in filenames:
                    source = (filestore / filename).resolve()
                    if not source.is_relative_to(filestore):
                        raise ValueError("Ruta de adjunto fuera del filestore")
                    destination = Path(dump_dir) / "filestore" / filename
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            with open(tmp_target, "wb") as stream:
                # dump.sql el primero dentro del zip: es lo que espera el
                # restaurador de Odoo para no tener que leerlo entero.
                zip_dir(dump_dir, stream, include_dir=False,
                        fnct_sort=lambda name: name != "dump.sql")
        with zipfile.ZipFile(tmp_target) as archive:
            if archive.testzip() or archive.getinfo("dump.sql").file_size == 0:
                raise ValueError("La comprobación del archivo ZIP ha fallado")
        os.replace(tmp_target, target)
        return os.path.getsize(target)

    @api.model
    def _mgs_run_backup(self, kind="auto"):
        """Hace una copia y deja constancia (también si falla)."""
        config = self.env["mgs.config"]._mgs_get()
        self.env.cr.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0))",
                            ["mgs-backup:" + self.env.cr.dbname])
        if not self.env.cr.fetchone()[0]:
            return self.browse()
        stamp = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        name = "%s-%s-%s.zip" % (self.env.cr.dbname, stamp.strftime("%Y%m%d-%H%M%S"), uuid4().hex[:8])
        try:
            directory = self._mgs_dir(config)
            target = os.path.join(directory, name)
            size = self._mgs_write_zip(target)
            checksum = self._mgs_checksum(target)
            Path(target + ".sha256").write_text(checksum + "  " + name + "\n", encoding="ascii")
            # Copia con nombre fijo: SIEMPRE el estado más reciente, para que
            # la tarea que sincroniza con el disco externo tenga una ruta
            # estable a la que apuntar.
            latest = self._mgs_latest_path(config)
            shutil.copyfile(target, latest + ".part")
            os.replace(latest + ".part", latest)
            Path(latest + ".sha256").write_text(checksum + "  " + Path(latest).name + "\n", encoding="ascii")
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
            "checksum": checksum,
            "message": _("Copia completa (base de datos + adjuntos). "
                         "Archivo permanente: %s", latest),
        })
        config.sudo().write({
            "backup_last_date": fields.Datetime.now(),
            "backup_last_path": target,
        })
        backup._mgs_replicate(config)
        self._mgs_purge(config)
        return backup

    @api.model
    def _mgs_purge(self, config=None):
        """Retención por días, únicamente archivos propios dentro de destinos activos."""
        config = config or self.env["mgs.config"]._mgs_get()
        cutoff = fields.Datetime.now() - timedelta(days=max(1, config.backup_retention_days or 30))
        old = self.sudo().search([("state", "=", "done"), ("date", "<", cutoff)])
        for backup in old:
            removed = True
            for filename, directory in [(backup.path, self._mgs_dir(config)),
                                        (backup.replica_path, config.backup_ssd_dir)]:
                if not filename:
                    continue
                if not directory or not Path(directory).is_dir():
                    removed = False
                    continue
                path = Path(filename).resolve()
                if not directory or path.parent != Path(directory).resolve() or path.name != backup.name:
                    removed = False
                    continue
                if not path.name.startswith(self.env.cr.dbname + "-") or path.suffix != ".zip":
                    removed = False
                    continue
                try:
                    path.unlink(missing_ok=True)
                    Path(str(path) + ".sha256").unlink(missing_ok=True)
                except OSError:
                    removed = False
                    _logger.exception("No se pudo aplicar la retención a %s", path)
            if removed:
                backup.unlink()

    def _mgs_replicate(self, config=None):
        self.ensure_one()
        config = config or self.env["mgs.config"]._mgs_get()
        if not config.backup_ssd_dir:
            return
        destination = Path(config.backup_ssd_dir).resolve()
        try:
            if not destination.is_dir():
                raise OSError("El SSD o su carpeta no están disponibles")
            if destination == Path(self.path).resolve().parent:
                raise ValueError("La copia local y la réplica SSD necesitan carpetas diferentes")
            target = destination / self.name
            temporary = Path(str(target) + ".part")
            shutil.copyfile(self.path, temporary)
            if self._mgs_checksum(temporary) != self.checksum:
                raise ValueError("La réplica SSD no coincide con la copia local")
            os.replace(temporary, target)
            Path(str(target) + ".sha256").write_text(self.checksum + "  " + self.name + "\n", encoding="ascii")
            self.sudo().write({"replica_state": "done", "replica_path": str(target),
                              "message": _("Copia local y réplica SSD verificadas.")})
        except Exception as err:
            self.sudo().write({"replica_state": "error", "message":
                _("Copia local correcta. Réplica SSD pendiente: %s", str(err))})
            _logger.warning("Réplica SSD pendiente: %s", err)

    # ------------------------------------------------------------------
    # Cron (data/mgs_hardware_data.xml)
    # ------------------------------------------------------------------
    @api.model
    def _mgs_backup_closed_sessions(self):
        if not self.env["mgs.config"]._mgs_get().backup_enabled:
            return False
        sessions = self.env["pos.session"].sudo().search([
            ("state", "=", "closed"), ("mgs_backup_pending", "=", True)])
        if not sessions:
            return False
        backup = self._mgs_run_backup(kind="close")
        if backup and backup.state == "done":
            sessions.write({"mgs_backup_pending": False})
        return backup

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
        # Recupera réplicas fallidas, con un límite para no saturar el inicio.
        for backup in self.sudo().search([("state", "=", "done"), ("replica_state", "=", "error")], limit=5):
            backup._mgs_replicate(config)
        closed_backup = self._mgs_backup_closed_sessions()
        if closed_backup:
            return closed_backup
        every = max(1, config.backup_every_hours or 6)
        last = self.sudo().search([("state", "=", "done")], order="date desc", limit=1)
        if last and last.date > fields.Datetime.now() - timedelta(hours=every):
            return False
        return self._mgs_run_backup(kind="auto")

    @api.model
    def _mgs_status_warning(self):
        config = self.env["mgs.config"]._mgs_get()
        if not config.backup_enabled:
            return _("Las copias automáticas están desactivadas.")
        last = self.sudo().search([], order="date desc, id desc", limit=1)
        if not last or last.state == "error":
            return _("No hay una copia reciente correcta. Revisa el historial de copias.")
        if last.date < fields.Datetime.now() - timedelta(hours=max(1, config.backup_every_hours or 6) + 1):
            return _("La última copia tiene más antigüedad de la prevista. Revisa las copias.")
        if not config.backup_ssd_dir:
            return _("La réplica en el SSD todavía no está configurada.")
        if last.replica_state != "done":
            return _("La copia local está guardada; falta comprobar la réplica en el SSD.")
        return False

    @api.model
    def action_mgs_backup_now(self):
        from .mgs_permissions import require_manager
        require_manager(self.env)
        """Botón «Hacer copia ahora» de la lista de copias."""
        backup = self._mgs_run_backup(kind="manual")
        if not backup:
            return {"type": "ir.actions.client", "tag": "display_notification",
                    "params": {"type": "warning", "message": _("Ya hay una copia en curso.")}}
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
