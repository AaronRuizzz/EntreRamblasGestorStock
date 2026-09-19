# -*- coding: utf-8 -*-
"""Carpetas de salida (models/mgs_output.py): informes y facturas van a su
propia carpeta en vez de mezclarse en la carpeta de Descargas del
navegador."""
import os
import shutil
import tempfile

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
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Informes")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, "Facturas")))

    def test_save_output_does_not_mix_informes_and_facturas(self):
        self.config._mgs_save_output("informes", "mismo-nombre.pdf", b"informe")
        self.config._mgs_save_output("facturas", "mismo-nombre.pdf", b"factura")
        with open(os.path.join(self.tmp_dir, "Informes", "mismo-nombre.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"informe")
        with open(os.path.join(self.tmp_dir, "Facturas", "mismo-nombre.pdf"), "rb") as handle:
            self.assertEqual(handle.read(), b"factura")

    def test_saving_the_same_filename_twice_keeps_both_instead_of_overwriting(self):
        first = self.config._mgs_save_output("informes", "repetido.csv", b"primero")
        second = self.config._mgs_save_output("informes", "repetido.csv", b"segundo")
        self.assertNotEqual(first, second)
        with open(first, "rb") as handle:
            self.assertEqual(handle.read(), b"primero")
        with open(second, "rb") as handle:
            self.assertEqual(handle.read(), b"segundo")

    def test_default_output_dir_is_under_the_users_documents_folder(self):
        # No se llama a _mgs_output_dir aquí (crearía la carpeta de verdad en
        # el equipo que ejecuta las pruebas): solo se comprueba la ruta.
        self.assertIn("Entre Ramblas", self.config._mgs_default_output_dir())

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
