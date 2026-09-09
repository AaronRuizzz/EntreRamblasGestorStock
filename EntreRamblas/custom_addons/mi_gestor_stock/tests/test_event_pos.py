from datetime import timedelta
from uuid import uuid4

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestEventPosCheckout(TestPointOfSaleCommon):
    """Cobrar un encargo en caja: mgs_event.action_mgs_checkout_pos,
    mgs_pos_load_event y la liquidación del pedido (pos.order._mgs_settle_event)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.customer = cls.env["res.partner"].create({"name": "Encargo de prueba"})
        cls.tax21 = cls.env["account.tax"].create({
            "name": "IVA 21 (test evento)", "amount": 21.0,
            "amount_type": "percent", "type_tax_use": "sale",
            "price_include_override": "tax_excluded",
        })
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa encargo", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "available_in_pos": True, "list_price": 5.0,
            "taxes_id": [Command.set(cls.tax21.ids)],
        })
        cls.arch = cls.env["product.product"].create({
            "name": "Arco encargo", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "mgs_rental_ok": True, "mgs_rental_deposit": 40.0,
            "list_price": 100.0,
        })
        cls.centre = cls.env["product.product"].create({
            "name": "Centro encargo", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "available_in_pos": True, "list_price": 10.0,
            "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.today = fields.Date.today()

    def _stock(self, product, quantity, cost=1.0, days=30):
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": self.today + timedelta(days=days),
        })]}).action_confirm()

    def _event(self, lines):
        start = self.today + timedelta(days=10)
        return self.env["mgs.event"].create({
            "partner_id": self.customer.id, "event_date": start,
            "return_date": start + timedelta(days=1), "line_ids": lines,
        })

    def _pos_order(self, event, product, qty, price_unit, paid):
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id,
            "amount_tax": 0, "amount_total": paid, "amount_paid": paid, "amount_return": 0,
            "mgs_event_ref": event.id,
            "lines": [Command.create({
                "product_id": product.id, "qty": qty, "price_unit": price_unit,
                "price_subtotal": qty * price_unit, "price_subtotal_incl": paid,
            })],
        })
        self.env["pos.payment"].create({
            "pos_order_id": order.id, "payment_method_id": self.cash_payment_method.id,
            "amount": paid,
        })
        order.state = "paid"
        order._create_order_picking()
        # En producción lo dispara pos.order._process_order / mgs_pos_link_order.
        order._mgs_settle_event()
        return order

    # ------------------------------------------------------------------
    def test_only_sellable_lines_in_draft_or_confirmed_are_chargeable(self):
        rental_only = self._event([Command.create({
            "product_id": self.arch.id, "is_rental": True, "quantity": 1, "unit_price": 100})])
        self.assertFalse(rental_only.mgs_pos_chargeable)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            rental_only.action_mgs_checkout_pos()

        mixed = self._event([
            Command.create({"product_id": self.arch.id, "is_rental": True, "quantity": 1, "unit_price": 100}),
            Command.create({"product_id": self.flower.id, "quantity": 6, "unit_price": 5}),
        ])
        self.assertTrue(mixed.mgs_pos_chargeable)
        action = mixed.action_mgs_checkout_pos()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("mgs_event=%d" % mixed.id, action["url"])

    def test_load_event_gives_net_prices_and_skips_rental(self):
        event = self._event([
            Command.create({"product_id": self.arch.id, "is_rental": True, "quantity": 1, "unit_price": 100}),
            Command.create({"product_id": self.flower.id, "quantity": 4, "unit_price": 6.05}),
        ])
        data = self.env["mgs.event"].mgs_pos_load_event(event.id)
        self.assertEqual(data["partner_id"], self.customer.id)
        self.assertEqual(len(data["lines"]), 1)  # el alquiler no va
        line = data["lines"][0]
        self.assertEqual(line["product_id"], self.flower.id)
        # 6,05 con IVA incluido -> 5,00 neto para que el ticket cuadre
        self.assertAlmostEqual(line["price_unit"], 5.0, places=2)

    def test_paying_in_pos_delivers_records_and_closes_when_no_rental(self):
        self._stock(self.flower, 20)
        event = self._event([Command.create({
            "product_id": self.flower.id, "quantity": 5, "unit_price": 5.0})])
        before = self.flower.qty_available
        self._pos_order(event, self.flower, 5, 5.0 / 1.21, paid=25.0)
        event.invalidate_recordset()
        self.assertEqual(event.state, "done")
        self.assertEqual(event.line_ids.delivered_qty, 5)
        self.assertEqual(len(event.payment_ids), 1)
        self.assertAlmostEqual(event.amount_paid, 25.0, places=2)
        self.assertAlmostEqual(event.amount_due, 0.0, places=2)
        self.assertEqual(self.flower.qty_available, before - 5)  # el TPV movió el stock

    def test_action_deliver_skips_lines_already_sold_in_pos(self):
        self._stock(self.flower, 20)
        self._stock(self.centre, 20)
        event = self._event([
            Command.create({"product_id": self.flower.id, "quantity": 4, "unit_price": 5.0}),
            Command.create({"product_id": self.centre.id, "quantity": 2, "unit_price": 10.0}),
        ])
        # La primera partida ya se vendió en caja (delivered_qty al completo).
        event.line_ids[0].sudo().write({"delivered_qty": 4})
        before_flower = self.flower.qty_available
        before_centre = self.centre.qty_available
        event.sudo().action_confirm()
        event.sudo().action_deliver()
        # Solo la segunda partida mueve stock; la ya vendida se salta.
        self.assertEqual(self.flower.qty_available, before_flower)
        self.assertEqual(self.centre.qty_available, before_centre - 2)
        self.assertEqual(event.state, "delivered")

    def test_settling_is_idempotent(self):
        self._stock(self.flower, 20)
        event = self._event([Command.create({
            "product_id": self.flower.id, "quantity": 3, "unit_price": 5.0})])
        order = self._pos_order(event, self.flower, 3, 5.0 / 1.21, paid=15.0)
        order._mgs_settle_event()
        order._mgs_settle_event()
        event.invalidate_recordset()
        self.assertEqual(len(event.payment_ids), 1)
