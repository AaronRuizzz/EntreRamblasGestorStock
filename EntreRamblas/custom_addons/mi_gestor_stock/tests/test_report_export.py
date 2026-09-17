# -*- coding: utf-8 -*-
"""Exportaciones del informe personalizado: pestañas del Excel, sello de
parcial/gestoría, y —lo importante— que un nombre de producto que parece una
fórmula acabe en una celda de TEXTO y no se ejecute al abrir el archivo."""
import base64
import io
import zipfile
from datetime import datetime
from uuid import uuid4

import pytz

from odoo import Command
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon

from ..models.mgs_report_template import GESTORIA_BANNER, PARTIAL_BANNER, GESTORIA_XML_ID

FORMULA_NAME = '=HYPERLINK("https://example.invalid","pincha")'


@tagged("post_install", "-at_install")
class TestReportExport(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa de exportación", "type": "service", "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.today = datetime.now(pytz.timezone("Europe/Madrid")).date()
        cls.gestoria = cls.env.ref(GESTORIA_XML_ID)

    def sale(self, product=None):
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 10, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": (product or self.flower).id, "qty": 1, "price_unit": 10,
                "price_subtotal": 10, "price_subtotal_incl": 10,
            })],
        })
        order.state = "paid"
        return order

    def template(self, **extra):
        vals = {"name": "Informe de la vitrina", "date_from": self.today, "date_to": self.today}
        vals.update(extra)
        return self.env["mgs.report.template"].create(vals)

    def sheets(self, template):
        """Las hojas del Excel generado, como {nombre: xml de la hoja}. Se lee
        el .xlsx como el zip que es, en vez de depender de openpyxl (que no
        está entre las dependencias del proyecto)."""
        template.action_export_excel()
        raw = base64.b64decode(template.xlsx_file)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertIsNone(archive.testzip())
            workbook = archive.read("xl/workbook.xml").decode("utf-8")
            names = [part.split('"')[0] for part in workbook.split('name="')[1:]]
            sheets = {}
            for index, name in enumerate(names, start=1):
                path = "xl/worksheets/sheet%d.xml" % index
                if path in archive.namelist():
                    sheets[name] = archive.read(path).decode("utf-8")
            shared = ""
            if "xl/sharedStrings.xml" in archive.namelist():
                shared = archive.read("xl/sharedStrings.xml").decode("utf-8")
        return sheets, shared

    # ------------------------------------------------------------------
    def test_a_product_named_like_a_formula_lands_in_a_text_cell(self):
        self.flower.name = FORMULA_NAME
        self.sale()
        template = self.template(group_by="product")
        sheets, shared = self.sheets(template)
        ventas = sheets["Ventas"]
        # El nombre viaja como cadena compartida...
        self.assertIn("HYPERLINK", shared)
        # ...y en la hoja no hay NI UNA celda de fórmula (<f>), que es lo que
        # Excel evaluaría al abrir el archivo.
        self.assertNotIn("<f>", ventas)
        self.assertNotIn("<f ", ventas)

    def test_only_the_selected_sections_get_a_tab(self):
        template = self.template(
            section_resumen=True, section_ventas=True, section_devoluciones=False,
            section_cobros=False, section_mermas=False, section_stock=False,
            section_consumo=False, section_eventos=False, section_correcciones=False)
        sheets, _shared = self.sheets(template)
        self.assertEqual(set(sheets), {"Resumen", "Ventas"})

    def test_a_custom_template_is_always_marked_as_partial(self):
        template = self.template()
        _sheets, shared = self.sheets(template)
        self.assertIn(PARTIAL_BANNER, shared)
        self.assertNotIn(GESTORIA_BANNER, shared)

    def test_the_locked_template_is_the_only_one_marked_for_gestoria(self):
        self.gestoria.write({"date_from": self.today, "date_to": self.today})
        _sheets, shared = self.sheets(self.gestoria)
        self.assertIn(GESTORIA_BANNER, shared)
        self.assertNotIn(PARTIAL_BANNER, shared)

    def test_the_excel_states_the_period_and_the_author(self):
        template = self.template()
        _sheets, shared = self.sheets(template)
        self.assertIn("Generado el", shared)
        self.assertIn(str(self.today), shared)
        self.assertIn("Sin filtros", shared)

    def test_pdf_renders_both_for_a_partial_and_for_the_locked_template(self):
        self.sale()
        template = self.template()
        html, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "mi_gestor_stock.report_mgs_report_builder_document", [template.id])
        self.assertIn(PARTIAL_BANNER.encode(), html)
        self.gestoria.write({"date_from": self.today, "date_to": self.today})
        html, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "mi_gestor_stock.report_mgs_report_builder_document", [self.gestoria.id])
        self.assertIn(GESTORIA_BANNER.encode(), html)

    def test_export_marks_nothing_about_the_lock_as_editable(self):
        # Generar el Excel de la plantilla bloqueada escribe el archivo en el
        # propio registro: eso lo hace el servidor y no puede chocar con el
        # candado (que solo frena ediciones de la usuaria).
        self.gestoria.action_export_excel()
        self.assertTrue(self.gestoria.xlsx_file)
        self.assertTrue(self.gestoria.xlsx_filename.endswith(".xlsx"))
