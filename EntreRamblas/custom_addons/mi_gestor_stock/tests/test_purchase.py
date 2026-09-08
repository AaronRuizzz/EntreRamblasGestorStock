from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged("post_install", "-at_install")
class TestPurchase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env["res.partner"].create({"name": "Mayorista de prueba"})
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa de pedido", "is_storable": True, "tracking": "lot",
            "use_expiration_date": True,
        })
        cls.green = cls.env["product.product"].create({
            "name": "Eucalipto de pedido", "is_storable": True, "tracking": "lot",
            "use_expiration_date": True,
        })

    def order(self, lines=None):
        return self.env["mgs.purchase.order"].create({
            "partner_id": self.supplier.id,
            "line_ids": lines if lines is not None else [
                Command.create({"product_id": self.rose.id, "quantity": 20, "unit_cost": 2.0}),
            ],
        })

    def receive(self, purchase, product, quantity, cost=2.0, days=3, supplier_ref=False, document_date=False):
        wizard = self.env["mgs.reception"].create({
            "purchase_id": purchase.id if purchase else False,
            "supplier_id": self.supplier.id,
            "supplier_ref": supplier_ref, "document_date": document_date,
            "line_ids": [Command.create({
                "product_id": product.id, "quantity": quantity, "unit_cost": cost,
                "expiry_date": fields.Date.today() + timedelta(days=days),
            })],
        })
        wizard.action_confirm()
        return wizard

    # ------------------------------------------------------------------
    def test_order_gets_a_sequential_name_and_starts_in_draft(self):
        purchase = self.order()
        self.assertTrue(purchase.name and purchase.name != "Nuevo")
        self.assertEqual(purchase.state, "draft")
        self.assertEqual(purchase.amount_total, 40.0)

    def test_confirming_needs_lines_and_positive_quantities(self):
        empty = self.env["mgs.purchase.order"].create({"partner_id": self.supplier.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            empty.action_confirm()
        purchase = self.order(lines=[Command.create(
            {"product_id": self.rose.id, "quantity": 0, "unit_cost": 2.0})])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            purchase.action_confirm()

    def test_partial_reception_updates_pending_and_state(self):
        purchase = self.order()
        purchase.action_confirm()
        self.assertEqual(purchase.state, "ordered")

        self.receive(purchase, self.rose, 12)
        self.assertEqual(purchase.state, "partial")
        line = purchase.line_ids
        self.assertEqual(line.received_qty, 12)
        self.assertEqual(line.pending_qty, 8)

        self.receive(purchase, self.rose, 8)
        self.assertEqual(purchase.state, "received")
        self.assertEqual(line.pending_qty, 0)

    def test_receiving_more_than_ordered_is_tracked_not_rejected(self):
        """Que llegue alguna unidad de más (redondeo, regalo del proveedor)
        no debe bloquear la recepción: se apunta igual, y lo pendiente no
        baja de cero."""
        purchase = self.order()
        purchase.action_confirm()
        self.receive(purchase, self.rose, 25)
        self.assertEqual(purchase.state, "received")
        self.assertEqual(purchase.line_ids.received_qty, 25)
        self.assertEqual(purchase.line_ids.pending_qty, 0)
        self.assertEqual(self.rose.qty_available, 25)

    def test_two_products_are_tracked_on_their_own_lines(self):
        purchase = self.order(lines=[
            Command.create({"product_id": self.rose.id, "quantity": 10, "unit_cost": 2.0}),
            Command.create({"product_id": self.green.id, "quantity": 5, "unit_cost": 1.0}),
        ])
        purchase.action_confirm()
        wizard = self.env["mgs.reception"].create({
            "purchase_id": purchase.id, "supplier_id": self.supplier.id,
            "line_ids": [
                Command.create({"product_id": self.rose.id, "quantity": 10, "unit_cost": 2.0}),
                Command.create({"product_id": self.green.id, "quantity": 5, "unit_cost": 1.0}),
            ],
        })
        wizard.action_confirm()
        self.assertEqual(purchase.state, "received")
        rose_line = purchase.line_ids.filtered(lambda l: l.product_id == self.rose)
        green_line = purchase.line_ids.filtered(lambda l: l.product_id == self.green)
        self.assertEqual(rose_line.received_qty, 10)
        self.assertEqual(green_line.received_qty, 5)

    def test_reception_carries_supplier_document_to_the_lot_and_picking(self):
        purchase = self.order()
        purchase.action_confirm()
        wizard = self.receive(purchase, self.rose, 20,
                              supplier_ref="ALB-778", document_date=fields.Date.today())
        lot = wizard.picking_id.move_line_ids.lot_id
        self.assertEqual(lot.mgs_supplier_ref, "ALB-778")
        self.assertEqual(lot.mgs_document_date, fields.Date.today())
        self.assertEqual(lot.mgs_supplier_id, self.supplier)
        self.assertEqual(wizard.picking_id.origin, purchase.name)
        # El coste y el origen, una vez recibidos, no se pueden retocar.
        with self.assertRaises(Exception), self.env.cr.savepoint():
            lot.write({"mgs_supplier_ref": "otro"})

    def test_reception_without_a_purchase_order_still_works(self):
        """No toda entrada viene de un pedido formal: sigue sin ser obligatorio."""
        wizard = self.env["mgs.reception"].create({
            "supplier_id": self.supplier.id,
            "line_ids": [Command.create({
                "product_id": self.rose.id, "quantity": 3, "unit_cost": 2.0,
            })],
        })
        wizard.action_confirm()
        self.assertEqual(self.rose.qty_available, 3)

    def test_confirmed_order_cannot_be_edited_away(self):
        purchase = self.order()
        purchase.action_confirm()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            purchase.write({"partner_id": self.supplier.id})
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            purchase.write({"state": "received"})
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            purchase.line_ids.write({"received_qty": 999})

    def test_a_received_order_cannot_be_cancelled(self):
        purchase = self.order()
        purchase.action_confirm()
        self.receive(purchase, self.rose, 20)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            purchase.action_cancel()

    def test_only_the_owner_manages_purchase_orders(self):
        staff = new_test_user(
            self.env(context=dict(self.env.context, no_reset_password=True)),
            login="purchase_staff", groups="mi_gestor_stock.group_mgs_user")
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["mgs.purchase.order"].with_user(staff).create({
                "partner_id": self.supplier.id,
            })
        purchase = self.order()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            purchase.with_user(staff).action_confirm()

    def test_create_rejects_fields_outside_the_whitelist(self):
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["mgs.purchase.order"].create({
                "partner_id": self.supplier.id, "state": "ordered",
            })
