from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBackup(TransactionCase):
    def test_retention_preserves_recent_and_unrelated_files(self):
        with TemporaryDirectory(prefix="mgs-retention-") as folder:
            root = Path(folder)
            local = root / "local"
            local.mkdir()
            config = self.env["mgs.config"]._mgs_get()
            config.write({"backup_dir": str(local), "backup_ssd_dir": False, "backup_retention_days": 30})
            files = []
            for label, directory, age in [("old", local, 31), ("recent", local, 29), ("outside", root, 31)]:
                path = directory / (self.env.cr.dbname + "-" + label + ".zip")
                path.write_bytes(b"test")
                files.append(path)
                self.env["mgs.backup"].create({"name": path.name, "path": str(path), "state": "done",
                    "date": fields.Datetime.now() - timedelta(days=age)})
            self.env["mgs.backup"]._mgs_purge(config)
            self.assertFalse(files[0].exists())
            self.assertTrue(files[1].exists())
            self.assertTrue(files[2].exists())

    def test_unplugged_ssd_preserves_local_and_recovers(self):
        with TemporaryDirectory(prefix="mgs-replica-") as folder:
            root = Path(folder)
            path = root / "backup.zip"
            path.write_bytes(b"local backup remains")
            config = self.env["mgs.config"]._mgs_get()
            config.backup_ssd_dir = str(root / "disconnected")
            backup = self.env["mgs.backup"].create({"name": path.name, "path": str(path), "state": "done",
                "checksum": self.env["mgs.backup"]._mgs_checksum(path)})
            backup._mgs_replicate(config)
            self.assertEqual(backup.state, "done")
            self.assertEqual(backup.replica_state, "error")
            self.assertEqual(path.read_bytes(), b"local backup remains")
            (root / "disconnected").mkdir()
            backup._mgs_replicate(config)
            self.assertEqual(backup.replica_state, "done")
            self.assertEqual(Path(backup.replica_path).read_bytes(), path.read_bytes())

    def test_ssd_folder_that_exists_but_cannot_be_written_gives_a_permissions_message(self):
        # Antes, Path.is_dir() devolvía False tanto si el disco estaba
        # desconectado como si estaba conectado pero sin permiso de
        # escritura, y el mensaje era el mismo para los dos casos ("El SSD o
        # su carpeta no están disponibles"). Aquí la carpeta SÍ existe: el
        # mensaje tiene que hablar de permisos, no de disco desconectado.
        with TemporaryDirectory(prefix="mgs-replica-perm-") as folder:
            root = Path(folder)
            path = root / "backup.zip"
            path.write_bytes(b"local backup remains")
            ssd = root / "ssd"
            ssd.mkdir()
            config = self.env["mgs.config"]._mgs_get()
            config.backup_ssd_dir = str(ssd)
            backup = self.env["mgs.backup"].create({"name": path.name, "path": str(path), "state": "done",
                "checksum": self.env["mgs.backup"]._mgs_checksum(path)})
            with patch("pathlib.Path.write_text", side_effect=PermissionError("Acceso denegado")):
                backup._mgs_replicate(config)
            self.assertEqual(backup.replica_state, "error")
            self.assertIn("permiso", backup.message)
            self.assertNotIn("no están disponibles", backup.message)

    def test_ssd_folder_without_enough_free_space_gives_a_clear_message(self):
        with TemporaryDirectory(prefix="mgs-replica-space-") as folder:
            root = Path(folder)
            path = root / "backup.zip"
            path.write_bytes(b"local backup remains")
            ssd = root / "ssd"
            ssd.mkdir()
            config = self.env["mgs.config"]._mgs_get()
            config.backup_ssd_dir = str(ssd)
            backup = self.env["mgs.backup"].create({
                "name": path.name, "path": str(path), "state": "done", "size": 10 * 1024 * 1024,
                "checksum": self.env["mgs.backup"]._mgs_checksum(path)})
            free_1kb = SimpleNamespace(total=0, used=0, free=1024)
            with patch("shutil.disk_usage", return_value=free_1kb):  # 1 KB libre
                backup._mgs_replicate(config)
            self.assertEqual(backup.replica_state, "error")
            self.assertIn("espacio", backup.message)

    def test_ssd_dir_equal_to_local_dir_is_rejected_without_touching_the_disk(self):
        with TemporaryDirectory(prefix="mgs-replica-same-") as folder:
            root = Path(folder)
            path = root / "backup.zip"
            path.write_bytes(b"local backup remains")
            config = self.env["mgs.config"]._mgs_get()
            config.backup_ssd_dir = str(root)
            backup = self.env["mgs.backup"].create({"name": path.name, "path": str(path), "state": "done",
                "checksum": self.env["mgs.backup"]._mgs_checksum(path)})
            backup._mgs_replicate(config)
            self.assertEqual(backup.replica_state, "error")
            self.assertIn("diferentes", backup.message)

    def test_action_mgs_test_ssd_checks_without_making_any_copy(self):
        with TemporaryDirectory(prefix="mgs-test-ssd-") as folder:
            ssd = Path(folder) / "ssd"
            ssd.mkdir()
            config = self.env["mgs.config"]._mgs_get()
            config.backup_ssd_dir = str(ssd)
            result = config.action_mgs_test_ssd()
            self.assertEqual(result["params"]["type"], "success")
            self.assertFalse(list(ssd.iterdir()))  # sin rastro: ni copia ni fichero de prueba

    def test_pre_update_backup_kind_is_accepted(self):
        # Hallazgo 6: el actualizador llama _mgs_run_backup(kind="pre-actualizacion"),
        # pero esa cadena no estaba en la Selection de "kind" -> ValueError al
        # crear el registro (mismo repro que probe_models.py de la auditoría).
        # La copia previa a actualizar quedaría bloqueada siempre.
        record = self.env["mgs.backup"].create({
            "name": "prueba-pre-actualizacion", "kind": "pre-actualizacion", "state": "done"})
        self.assertEqual(record.kind, "pre-actualizacion")

    def test_run_backup_records_the_pre_update_kind_on_failure_too(self):
        # El camino de error de _mgs_run_backup también crea el registro con
        # el kind recibido: debe admitir "pre-actualizacion" igual que "auto".
        with patch.object(type(self.env["mgs.backup"]), "_mgs_write_zip",
                          side_effect=OSError("Disco lleno")):
            result = self.env["mgs.backup"]._mgs_run_backup(kind="pre-actualizacion")
        self.assertEqual(result.state, "error")
        self.assertEqual(result.kind, "pre-actualizacion")

    def test_failed_backup_is_visible_without_raising(self):
        with patch.object(type(self.env["mgs.backup"]), "_mgs_write_zip", side_effect=OSError("Disco lleno")):
            result = self.env["mgs.config"]._mgs_get().action_mgs_backup_now()
        self.assertEqual(result["params"]["type"], "danger")
        self.assertTrue(self.env["mgs.backup"].search([("state", "=", "error"), ("message", "=", "Disco lleno")]))

    def test_list_header_backup_button_accepts_the_selection_argument(self):
        # Odoo pasa la selección de la lista al botón de cabecera, aun cuando
        # el botón no necesita una copia ya existente para funcionar.
        Backup = self.env["mgs.backup"]
        with patch.object(type(Backup), "_mgs_run_backup", return_value=Backup):
            result = Backup.action_mgs_backup_now([])
        self.assertEqual(result["params"]["type"], "warning")
