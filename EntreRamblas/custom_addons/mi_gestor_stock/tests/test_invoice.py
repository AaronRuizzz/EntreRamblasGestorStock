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
from uuid import uuid4

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestInvoiceLegalData(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spain = cls.env.ref("base.es")
        cls.env.company.write({
            "vat": "ESB83355065", "street": "Calle Mayor 1", "city": "Barcelona",
            "zip": "08001", "country_id": spain.id,
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Clienta con factura",
            "vat": "ESB39118237", "street": "Calle Luna 2", "city": "Madrid",
            "zip": "28001", "country_id": spain.id,
        })
        cls.income_account = cls.env["account.account"].search([
            ("account_type", "=", "income"), ("company_ids", "in", cls.env.company.id),
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

    def test_an_invoice_to_a_customer_without_zip_or_country_cannot_be_posted(self):
        partner_incompleto = self.env["res.partner"].create({
            "name": "Clienta sin CP", "vat": "ESB11111112",
            "street": "Calle Sin CP 1", "city": "Vigo",
        })
        move = self.invoice(partner=partner_incompleto)
        with self.assertRaises(UserError):
            move.action_post()

    def test_an_invoice_cannot_be_posted_if_the_shop_is_missing_zip_or_country(self):
        self.env.company.zip = False
        move = self.invoice()
        with self.assertRaises(UserError):
            move.action_post()

    def test_an_invoice_without_a_payment_term_cannot_be_posted(self):
        # Empresa: no recibe "al contado" por defecto (solo particulares,
        # res_partner.py), así que hay que quitárselo a mano para probar
        # el hueco.
        empresa = self.env["res.partner"].create({
            "name": "Floristería Mayorista SL", "is_company": True,
            "vat": "ESB22222223", "street": "Polígono Norte 3", "city": "Getafe",
            "zip": "28901", "country_id": self.env.ref("base.es").id,
        })
        empresa.property_payment_term_id = False
        move = self.invoice(partner=empresa)
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
        spain = cls.env.ref("base.es")
        cls.env.company.write({
            "vat": "ESB83355065", "street": "Calle Mayor 1", "city": "Barcelona",
            "zip": "08001", "country_id": spain.id,
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Clienta con factura",
            "vat": "ESB39118237", "street": "Calle Luna 2", "city": "Madrid",
            "zip": "28001", "country_id": spain.id,
        })
        cls.income_account = cls.env["account.account"].search([
            ("account_type", "=", "income"), ("company_ids", "in", cls.env.company.id),
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


@tagged("post_install", "-at_install")
class TestInvoiceFromPos(TestPointOfSaleCommon):
    """`_mgs_check_legal_data` se comprueba en `_post()`, no en
    `action_post()`: el TPV factura llamando a `pos.order.action_pos_order_invoice`
    → `_generate_pos_order_invoice` → `_post()` directamente
    (point_of_sale/models/pos_order.py), sin pasar nunca por `action_post()`.
    Antes de moverlo, ese camino se saltaba la validación legal por
    completo; estas pruebas recorren el camino real, no solo el del
    backend (que es el que ya cubría TestInvoiceLegalData y que NUNCA
    reprodujo el hueco)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spain = cls.env.ref("base.es")
        cls.env.company.write({
            "vat": "ESB83355065", "street": "Calle Mayor 1", "city": "Barcelona",
            "zip": "08001", "country_id": spain.id,
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.flower = cls.env["product.product"].create({
            "name": "Ramo de prueba (TPV)", "available_in_pos": True, "list_price": 10.0,
        })

    def _paid_order(self, partner):
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id,
            "partner_id": partner.id,
            "amount_tax": 0, "amount_total": 10.0, "amount_paid": 10.0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.flower.id, "qty": 1, "price_unit": 10.0,
                "price_subtotal": 10.0, "price_subtotal_incl": 10.0,
            })],
        })
        self.env["pos.payment"].create({
            "pos_order_id": order.id, "payment_method_id": self.cash_payment_method.id,
            "amount": 10.0,
        })
        order.state = "paid"
        return order

    def test_invoicing_from_the_pos_without_legal_data_raises_a_clear_error(self):
        partner_sin_datos = self.env["res.partner"].create({"name": "Clienta de caja sin datos"})
        order = self._paid_order(partner_sin_datos)
        with self.assertRaises(UserError):
            order.action_pos_order_invoice()

    def test_invoicing_from_the_pos_with_complete_data_posts_and_uses_the_payment_term(self):
        spain = self.env.ref("base.es")
        partner = self.env["res.partner"].create({
            "name": "Clienta de caja con factura",
            "vat": "ESB39118237", "street": "Calle Luna 2", "city": "Madrid",
            "zip": "28001", "country_id": spain.id,
        })
        # Particular: res_partner.py ya le ha puesto "al contado" al crearla.
        immediate = self.env.ref("account.account_payment_term_immediate")
        self.assertEqual(partner.property_payment_term_id, immediate)

        order = self._paid_order(partner)
        order.action_pos_order_invoice()
        move = order.account_move
        self.assertTrue(move)
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.invoice_payment_term_id, immediate)

    def test_pos_invoice_does_not_require_enterprise_deferred_dates(self):
        """Reproducción del error visto en caja: Community no instala los
        campos de periodificación de Enterprise, pero Factur-X los consultaba
        al emitir una factura desde TPV."""
        spain = self.env.ref("base.es")
        partner = self.env["res.partner"].create({
            "name": "Empresa de caja", "is_company": True,
            "vat": "ESB39118237", "street": "Calle Luna 2", "city": "Madrid",
            "zip": "28001", "country_id": spain.id,
            "property_payment_term_id": self.env.ref("account.account_payment_term_immediate").id,
        })
        order = self._paid_order(partner)
        order.action_pos_order_invoice()
        move = order.account_move
        self.assertNotIn("deferred_start_date", self.env["account.move.line"]._fields)
        period = self.env["account.edi.cii"]._cii_get_billing_specified_period_node({"invoice": move})
        self.assertIn("ram:StartDateTime", period)
        self.assertIn("ram:EndDateTime", period)
