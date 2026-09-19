# -*- coding: utf-8 -*-
"""Informes -> Clientes (views/mgs_partner_views.xml): "un sitio donde
consultar los clientes, y con ellos, sus facturas". Solo cubre lo propio de
esta pantalla (dominio de la acción, permiso de escritura acotado sobre
account.move); el contenido de la factura en sí ya lo cubre test_invoice.py."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import safe_eval


@tagged("post_install", "-at_install")
class TestReportClients(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, login="mgs_clients_manager", groups="mi_gestor_stock.group_mgs_manager")
        cls.income_account = cls.env["account.account"].search([
            ("account_type", "=", "income"), ("company_ids", "in", cls.env.company.id),
        ], limit=1)

    def test_the_clients_action_only_shows_partners_with_purchases(self):
        action = self.env.ref("mi_gestor_stock.action_mgs_report_clients")
        never_bought = self.env["res.partner"].create({"name": "Nunca ha comprado"})
        move = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.env["res.partner"].create({"name": "Sí ha comprado"}).id,
            "invoice_line_ids": [Command.create({
                "name": "Ramo", "quantity": 1, "price_unit": 10.0,
                "account_id": self.income_account.id,
            })],
        })
        move.action_post()  # confirmar la factura sube customer_rank
        domain = safe_eval(action.domain)
        found = self.env["res.partner"].search(domain)
        self.assertIn(move.partner_id, found)
        self.assertNotIn(never_bought, found)

    def test_the_manager_can_change_the_payment_term_of_a_draft_invoice(self):
        partner = self.env["res.partner"].create({"name": "Clienta con encargo pendiente"})
        move = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": partner.id,
            "invoice_line_ids": [Command.create({
                "name": "Ramo", "quantity": 1, "price_unit": 10.0,
                "account_id": self.income_account.id,
            })],
        })
        thirty_days = self.env["account.payment.term"].create({"name": "30 días (test)"})
        move.with_user(self.manager).invoice_payment_term_id = thirty_days
        self.assertEqual(move.invoice_payment_term_id, thirty_days)

    def test_a_user_without_the_manager_group_cannot_write_invoices(self):
        staff = new_test_user(
            self.env, login="mgs_clients_staff", groups="mi_gestor_stock.group_mgs_user")
        partner = self.env["res.partner"].create({"name": "Clienta staff"})
        move = self.env["account.move"].create({
            "move_type": "out_invoice", "partner_id": partner.id,
            "invoice_line_ids": [Command.create({
                "name": "Ramo", "quantity": 1, "price_unit": 10.0,
                "account_id": self.income_account.id,
            })],
        })
        with self.assertRaises(AccessError):
            move.with_user(staff).invoice_date_due = "2030-01-01"
