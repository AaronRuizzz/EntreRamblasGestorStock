# -*- coding: utf-8 -*-
"""Factura completa (models/mgs_account_move.py): sin NIF ni domicilio, ni de
la tienda ni del cliente, no se deja confirmar; con los datos completos, el
documento lleva el desglose de IVA (nativo, account.document_tax_totals) y,
en una rectificativa, la referencia a la factura que rectifica (lo único que
la plantilla nativa no señalaba de forma legible).

No activa VERI*FACTU: eso sigue siendo la decisión aplazada de
FACTURACION.md."""
import os
import shutil
import tempfile

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestInvoiceLegalData(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({
            "vat": "ESB83355065", "street": "Calle Mayor 1", "city": "Barcelona",
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Clienta con factura",
            "vat": "ESB39118237", "street": "Calle Luna 2", "city": "Madrid",
        })
        cls.income_account = cls.env["account.account"].search([
            ("account_type", "=", "income"), ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def invoice(self, partner=None, move_type="out_invoice", reversed_entry_id=False):
        return self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": (partner or self.partner).id,
            "reversed_entry_id": reversed_entry_id.id if reversed_entry_id else False,
            "invoice_line_ids": [Command.create({
                "name": "Ramo de prueba", "quantity": 1, "price_unit": 10.0,
                "account_id": self.income_account.id,
            })],
        })

    def test_an_invoice_to_a_customer_without_vat_or_address_cannot_be_posted(self):
        partner_sin_datos = self.env["res.partner"].create({"name": "Clienta sin datos"})
        move = self.invoice(partner=partner_sin_datos)
        with self.assertRaises(UserError):
            move.action_post()

    def test_an_invoice_cannot_be_posted_if_the_shop_is_missing_legal_data(self):
        self.env.company.vat = False
        move = self.invoice()
        with self.assertRaises(UserError):
            move.action_post()

    def test_a_complete_invoice_posts_without_errors(self):
        move = self.invoice()
        move.action_post()
        self.assertEqual(move.state, "posted")

    def test_a_credit_note_shows_which_invoice_it_rectifies(self):
        original = self.invoice()
        original.action_post()
        credit_note = self.invoice(move_type="out_refund", reversed_entry_id=original)
        credit_note.action_post()
        html, report_type = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice_document", credit_note.ids)
        self.assertEqual(report_type, "html")
        self.assertIn(("Rectifica la factura " + original.name).encode(), html)

        # Una factura normal (no rectificativa) no lleva ese aviso.
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            "account.report_invoice_document", original.ids)
        self.assertNotIn(b"Rectifica la factura", html)


@tagged("post_install", "-at_install")
class TestInvoicePdfSavesToTheFacturasFolder(TransactionCase):
    """Cubre action_mgs_invoice_pdf de punta a punta: PDF real (necesita
    wkhtmltopdf, ya presente en este entorno de desarrollo — ver
    install-pdf.ps1 — de ahí `force_report_rendering`, que se salta el
    render en HTML con el que Odoo sustituye al PDF durante las pruebas
    automáticas) guardado en la carpeta Facturas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({
            "vat": "ESB83355065", "street": "Calle Mayor 1", "city": "Barcelona",
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Clienta con factura",
            "vat": "ESB39118237", "street": "Calle Luna 2", "city": "Madrid",
        })
        cls.income_account = cls.env["account.account"].search([
            ("account_type", "=", "income"), ("company_id", "=", cls.env.company.id),
        ], limit=1)

    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.mkdtemp(prefix="mgs-invoice-test-")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)
        self.env["mgs.config"]._mgs_get().output_dir = self.tmp_dir

    def test_the_generated_pdf_is_saved_in_the_facturas_folder(self):
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_line_ids": [Command.create({
                "name": "Ramo de prueba", "quantity": 1, "price_unit": 10.0,
                "account_id": self.income_account.id,
            })],
        })
        move.action_post()
        action = move.with_context(force_report_rendering=True).action_mgs_invoice_pdf()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("download=true", action["url"])
        expected = os.path.join(self.tmp_dir, "Facturas", "%s.pdf" % move.name.replace("/", "-"))
        self.assertTrue(os.path.isfile(expected))
        with open(expected, "rb") as handle:
            self.assertTrue(handle.read().startswith(b"%PDF-"))
