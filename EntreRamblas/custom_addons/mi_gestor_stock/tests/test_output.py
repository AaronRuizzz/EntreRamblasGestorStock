# -*- coding: utf-8 -*-
"""Carpetas de salida (models/mgs_output.py): informes y facturas van a su
propia carpeta en vez de mezclarse en la carpeta de Descargas del
navegador."""
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOutputFolders(TransactionCase):
    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.mkdtemp(prefix="mgs-output-test-")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.config = self.env["mgs.config"]._mgs_get()
        self.config.output_dir = self.tmp_dir

    def test_save_output_creates_the_informes_and_facturas_subfolders(self):
        self.config._mgs_save_output("informes", "test.pdf", b"contenido informe")
        self.config._mgs_save_output("facturas", "test.pdf", b"contenido factura")
        self.config._mgs_save_output("tickets", "test.pdf", b"contenido ticket")
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Informes")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Facturas")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Tickets")))

    def test_save_output_does_not_mix_informes_and_facturas(self):
        self.config._mgs_save_output("informes", "mismo-nombre.pdf", b"informe")
        self.config._mgs_save_output("facturas", "mismo-nombre.pdf", b"factura")
        self.config._mgs_save_output("tickets", "mismo-nombre.pdf", b"ticket")
        with open(os.path.join(self.tmp_dir, "Informes", "mismo-nombre.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"informe")
        with open(os.path.join(self.tmp_dir, "Facturas", "mismo-nombre.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"factura")
        with open(os.path.join(self.tmp_dir, "Tickets", "mismo-nombre.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"ticket")

    def test_saving_the_same_filename_twice_keeps_both_instead_of_overwriting(self):
        first = self.config._mgs_save_output("informes", "repetido.csv", b"primero")
        second = self.config._mgs_save_output("informes", "repetido.csv", b"segundo")
        self.assertNotEqual(first, second)
        with open(first, "rb") as handle:
            self.assertEqual(handle.read(), b"primero")
        with open(second, "rb") as handle:
            self.assertEqual(handle.read(), b"segundo")

    def test_prepare_output_folders_creates_both_folders(self):
        result = self.config.action_mgs_prepare_output_folders()
        self.assertEqual(result["tag"], "display_notification")
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Facturas")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Informes")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Tickets")))

    def test_default_output_dir_is_the_managed_documents_folder(self):
        # No se llama a _mgs_output_dir aquí (crearía la carpeta de verdad en
        # el equipo que ejecuta las pruebas): solo se comprueba la ruta.
        default = self.config._mgs_default_output_dir()
        self.assertTrue(default.endswith(os.path.join("EntreRamblas", "Documentos")))
        if os.name == "nt":
            self.assertTrue(default.lower().startswith(
                (os.environ.get("ProgramData") or r"C:\ProgramData").lower()))

    def test_check_folders_and_no_open_folder_actions(self):
        self.assertEqual(self.config.action_mgs_check_output_folders()["tag"], "display_notification")
        for name in ("invoices", "reports", "tickets"):
            self.assertFalse(hasattr(self.config, "action_mgs_open_%s_folder" % name))

    def test_a_file_where_a_folder_should_be_gives_a_clear_error(self):
        with open(os.path.join(self.tmp_dir, "Informes"), "wb") as handle:
            handle.write(b"no soy una carpeta")
        with self.assertRaises(UserError) as caught:
            self.config._mgs_save_output("informes", "x.pdf", b"x")
        self.assertIn("archivo donde debería haber una carpeta", str(caught.exception))

    def test_reserved_windows_names_are_rejected(self):
        for name in ("CON.pdf", "nul.txt", "COM1.csv", "", ".."):
            with self.assertRaises(UserError, msg=name):
                self.config._mgs_save_output("informes", name, b"x")

    def test_missing_permissions_give_a_clear_error(self):
        with patch("odoo.addons.mi_gestor_stock.models.mgs_output.os.makedirs",
                   side_effect=PermissionError("denegado")):
            with self.assertRaises(UserError) as caught:
                self.config._mgs_output_dir("tickets")
        self.assertIn("permiso", str(caught.exception))

    def test_unavailable_disk_gives_a_clear_error(self):
        with patch("odoo.addons.mi_gestor_stock.models.mgs_output.os.makedirs",
                   side_effect=OSError("disco no disponible")):
            with self.assertRaises(UserError):
                self.config._mgs_output_dir("facturas")

    def test_low_disk_space_is_reported(self):
        with patch("odoo.addons.mi_gestor_stock.models.mgs_output.shutil.disk_usage",
                   return_value=SimpleNamespace(free=1024)):
            with self.assertRaises(UserError):
                self.config._mgs_output_dir("facturas")

    def test_legacy_documents_are_copied_without_touching_the_originals(self):
        old_base = tempfile.mkdtemp(prefix="mgs-old-")
        self.addCleanup(shutil.rmtree, old_base, ignore_errors=True)
        for folder, name, data in (("Facturas", "f.pdf", b"factura"),
                                   ("Informes", "i.csv", b"informe"),
                                   ("Tickets", "t.pdf", b"ticket")):
            os.makedirs(os.path.join(old_base, folder))
            with open(os.path.join(old_base, folder, name), "wb") as handle:
                handle.write(data)
        # El mismo nombre ya existe en destino con OTRO contenido.
        os.makedirs(os.path.join(self.tmp_dir, "Facturas"))
        with open(os.path.join(self.tmp_dir, "Facturas", "f.pdf"), "wb") as handle:
            handle.write(b"distinta")

        copied = self.config._mgs_copy_legacy_documents(old_base, self.tmp_dir)
        self.assertEqual(copied, 3)
        with open(os.path.join(self.tmp_dir, "Facturas", "f.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"distinta")
        with open(os.path.join(self.tmp_dir, "Facturas", "f-2.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"factura")
        self.assertTrue(os.path.isfile(os.path.join(old_base, "Facturas", "f.pdf")))
        # Repetir la migración no duplica nada.
        self.assertEqual(self.config._mgs_copy_legacy_documents(old_base, self.tmp_dir), 0)
        self.assertFalse(os.path.exists(os.path.join(self.tmp_dir, "Facturas", "f-3.pdf")))

    def test_monthly_report_csv_export_lands_in_the_informes_folder(self):
        report = self.env["mgs.monthly.report"].create({})
        report.action_export_csv()
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp_dir, "Informes", report.csv_filename)))

    def test_monthly_report_zip_export_lands_in_the_informes_folder(self):
        report = self.env["mgs.monthly.report"].create({})
        report.action_export_all_csv()
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp_dir, "Informes", report.export_filename)))
