# -*- coding: utf-8 -*-
"""Correcciones trazables: una venta nunca se borra, la devolución tiene que
estar vinculada de verdad, el cobro original no se toca, y el efectivo
esperado solo se ajusta si la caja sigue abierta."""
from datetime import datetime
from uuid import uuid4

import pytz

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged, new_test_user
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon

from ..models import mgs_report_engine as engine


@tagged("post_install", "-at_install")
class TestCorrection(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa de corrección", "type": "service", "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.today = datetime.now(pytz.timezone("Europe/Madrid")).date()
        cls.clerk = new_test_user(
            cls.env, login="mgs_correction_clerk",
            groups="mi_gestor_stock.group_mgs_user")

    def order(self, quantity=1, original_line=False):
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id, "amount_tax": 0,
            "amount_total": quantity * 10, "amount_paid": quantity * 10, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.flower.id, "qty": quantity, "price_unit": 10,
                "price_subtotal": quantity * 10, "price_subtotal_incl": quantity * 10,
                "refunded_orderline_id": original_line.id if original_line else False,
            })],
        })
        order.state = "paid"
        return order

    def payment(self, order, method, amount=10):
        return self.env["pos.payment"].create({
            "pos_order_id": order.id, "payment_method_id": method.id, "amount": amount,
        })

    def wizard(self, **values):
        return self.env["mgs.correction.wizard"].create(values)

    # ------------------------------------------------------------------
    # Corrección de venta
    # ------------------------------------------------------------------
    def test_a_linked_refund_records_the_correction(self):
        sale = self.order(2)
        refund = self.order(-1, original_line=sale.lines)
        action = self.wizard(
            correction_type="sale", reason="Se cobraron 2 ramos en vez de 1.",
            original_order_id=sale.id, return_order_id=refund.id).action_apply()
        correction = self.env["mgs.correction"].browse(action["res_id"])
        self.assertTrue(correction.name.startswith("CORR/"))
        self.assertEqual(correction.original_order_id, sale)
        self.assertEqual(correction.return_order_id, refund)
        self.assertEqual(correction.original_value, sale.amount_total)
        self.assertEqual(correction.resulting_value, sale.amount_total + refund.amount_total)
        self.assertEqual(correction.user_id, self.env.user)
        # La venta original sigue ahí, intacta.
        self.assertEqual(sale.state, "paid")
        self.assertEqual(sale.amount_total, 20)

    def test_an_unrelated_refund_is_rejected(self):
        sale = self.order(2)
        other_sale = self.order(3)
        unrelated_refund = self.order(-1, original_line=other_sale.lines)
        with self.assertRaises(UserError):
            self.wizard(correction_type="sale", reason="Motivo",
                        original_order_id=sale.id,
                        return_order_id=unrelated_refund.id).action_apply()

    def test_a_reason_is_always_required(self):
        sale = self.order(2)
        refund = self.order(-1, original_line=sale.lines)
        with self.assertRaises(UserError):
            self.wizard(correction_type="sale", reason="   ",
                        original_order_id=sale.id, return_order_id=refund.id).action_apply()

    def test_the_replacement_sale_is_linked_when_there_is_one(self):
        sale = self.order(1)
        refund = self.order(-1, original_line=sale.lines)
        replacement = self.order(1)
        action = self.wizard(
            correction_type="sale", reason="Producto equivocado: se rehace la venta.",
            original_order_id=sale.id, return_order_id=refund.id,
            new_sale_order_id=replacement.id).action_apply()
        correction = self.env["mgs.correction"].browse(action["res_id"])
        self.assertEqual(correction.new_sale_order_id, replacement)
        self.assertIn(replacement.name, correction.result_note)

    # ------------------------------------------------------------------
    # Reclasificación de cobro
    # ------------------------------------------------------------------
    def test_cash_to_card_on_an_open_session_adjusts_expected_cash(self):
        self.session.set_opening_control(0, "")
        order = self.order(1)
        payment = self.payment(order, self.cash_payment_method, 10)
        expected_before = self.session.cash_register_balance_end
        action = self.wizard(
            correction_type="payment_method", reason="Se pagó con tarjeta, no en efectivo.",
            original_payment_id=payment.id,
            corrected_method_id=self.bank_payment_method.id, amount=10).action_apply()
        correction = self.env["mgs.correction"].browse(action["res_id"])
        self.session.invalidate_recordset()
        # El cobro original se conserva tal cual.
        self.assertEqual(payment.payment_method_id, self.cash_payment_method)
        self.assertEqual(payment.amount, 10)
        # Y el efectivo esperado baja esos 10 €.
        self.assertTrue(correction.statement_line_id)
        self.assertEqual(correction.statement_line_id.amount, -10)
        self.assertEqual(self.session.cash_register_balance_end, expected_before - 10)
        self.assertTrue(correction.session_was_open)

    def test_card_to_cash_on_an_open_session_raises_expected_cash(self):
        self.session.set_opening_control(0, "")
        order = self.order(1)
        payment = self.payment(order, self.bank_payment_method, 10)
        expected_before = self.session.cash_register_balance_end
        self.wizard(
            correction_type="payment_method", reason="Pagó en efectivo.",
            original_payment_id=payment.id,
            corrected_method_id=self.cash_payment_method.id, amount=10).action_apply()
        self.session.invalidate_recordset()
        self.assertEqual(self.session.cash_register_balance_end, expected_before + 10)

    def test_a_reclassification_between_two_non_cash_methods_leaves_the_till_alone(self):
        self.session.set_opening_control(0, "")
        order = self.order(1)
        payment = self.payment(order, self.bank_payment_method, 10)
        expected_before = self.session.cash_register_balance_end
        statement_lines_before = self.session.statement_line_ids
        action = self.wizard(
            correction_type="payment_method", reason="Era la otra tarjeta.",
            original_payment_id=payment.id,
            corrected_method_id=self.credit_payment_method.id, amount=10).action_apply()
        correction = self.env["mgs.correction"].browse(action["res_id"])
        self.session.invalidate_recordset()
        self.assertFalse(correction.statement_line_id)
        self.assertEqual(self.session.statement_line_ids, statement_lines_before)
        self.assertEqual(self.session.cash_register_balance_end, expected_before)

    def test_a_closed_session_is_never_reopened_or_rewritten(self):
        self.session.set_opening_control(0, "")
        order = self.order(1)
        payment = self.payment(order, self.cash_payment_method, 10)
        self.session.action_pos_session_close()
        self.assertEqual(self.session.state, "closed")
        closed_expected = self.session.cash_register_balance_end
        statement_lines_before = self.session.statement_line_ids
        action = self.wizard(
            correction_type="payment_method", reason="Se anotó en efectivo por error.",
            original_payment_id=payment.id,
            corrected_method_id=self.bank_payment_method.id, amount=10).action_apply()
        correction = self.env["mgs.correction"].browse(action["res_id"])
        self.session.invalidate_recordset()
        # Ni apunte nuevo, ni cierre tocado, ni sesión reabierta.
        self.assertFalse(correction.statement_line_id)
        self.assertFalse(correction.session_was_open)
        self.assertEqual(self.session.statement_line_ids, statement_lines_before)
        self.assertEqual(self.session.state, "closed")
        self.assertEqual(self.session.cash_register_balance_end, closed_expected)
        # Pero la reclasificación queda registrada para conciliarla.
        self.assertEqual(correction.corrected_method_id, self.bank_payment_method)
        self.assertIn("cerrada", correction.result_note)

    def test_reclassifying_more_than_was_charged_is_rejected(self):
        self.session.set_opening_control(0, "")
        order = self.order(1)
        payment = self.payment(order, self.cash_payment_method, 10)
        with self.assertRaises(UserError):
            self.wizard(correction_type="payment_method", reason="Motivo",
                        original_payment_id=payment.id,
                        corrected_method_id=self.bank_payment_method.id,
                        amount=25).action_apply()

    def test_reclassifying_to_the_same_method_is_rejected(self):
        order = self.order(1)
        payment = self.payment(order, self.cash_payment_method, 10)
        with self.assertRaises(UserError):
            self.wizard(correction_type="payment_method", reason="Motivo",
                        original_payment_id=payment.id,
                        corrected_method_id=self.cash_payment_method.id,
                        amount=10).action_apply()

    # ------------------------------------------------------------------
    # Inmutabilidad, permisos e informe
    # ------------------------------------------------------------------
    def correction(self):
        sale = self.order(1)
        refund = self.order(-1, original_line=sale.lines)
        action = self.wizard(
            correction_type="sale", reason="Cantidad mal cobrada.",
            original_order_id=sale.id, return_order_id=refund.id).action_apply()
        return self.env["mgs.correction"].browse(action["res_id"])

    def test_a_correction_can_never_be_modified_or_deleted(self):
        correction = self.correction()
        with self.assertRaises(AccessError):
            correction.write({"reason": "otra cosa"})
        with self.assertRaises(AccessError):
            correction.sudo().write({"reason": "otra cosa"})
        with self.assertRaises(AccessError):
            correction.unlink()

    def test_corrections_cannot_be_created_outside_the_wizard(self):
        with self.assertRaises(AccessError):
            self.env["mgs.correction"].create({
                "correction_type": "sale", "reason": "A mano", "company_id": self.env.company.id})

    def test_a_clerk_cannot_confirm_a_correction(self):
        sale = self.order(1)
        refund = self.order(-1, original_line=sale.lines)
        # La dependienta no llega ni a abrir el asistente: el permiso del
        # modelo ya se lo impide.
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["mgs.correction.wizard"].with_user(self.clerk).create({
                "correction_type": "sale", "reason": "Intento de dependienta",
                "original_order_id": sale.id, "return_order_id": refund.id,
            })
        # Y si el asistente le llegara ya creado (una acción compartida, un
        # id reutilizado), require_manager lo corta igual al confirmarlo:
        # el permiso no depende solo de la lista de accesos.
        wizard = self.wizard(
            correction_type="sale", reason="Intento de dependienta",
            original_order_id=sale.id, return_order_id=refund.id)
        with self.assertRaises(AccessError):
            wizard.with_user(self.clerk).action_apply()

    def test_the_report_shows_the_original_the_correction_and_the_result(self):
        correction = self.correction()
        template = self.env["mgs.report.template"].create({
            "name": "Con correcciones", "date_from": self.today, "date_to": self.today,
        })
        rows = engine.build(template)["correcciones"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], correction.name)
        self.assertEqual(row["original_value"], correction.original_value)
        self.assertEqual(row["corrected_value"], correction.corrected_value)
        self.assertEqual(row["resulting_value"], correction.resulting_value)
        self.assertEqual(row["reason"], "Cantidad mal cobrada.")
        # Y la vista previa las cuenta.
        template.action_refresh_preview()
        self.assertEqual(template.preview_corrections_count, 1)
