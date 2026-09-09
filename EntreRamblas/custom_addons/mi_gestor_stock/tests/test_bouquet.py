import json
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, AccessError, ValidationError
from odoo.tests import tagged, new_test_user
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestBouquet(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa de ramo", "tracking": "lot", "mgs_auto_lots": True,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
            "list_price": 2.0,
        })
        cls.green = cls.env["product.product"].create({
            "name": "Eucalipto de ramo", "tracking": "lot", "mgs_auto_lots": True,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
            "list_price": 1.0,
        })
        cls.bouquet = cls.env["product.product"].create({
            "name": "Ramo de prueba", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "available_in_pos": True,
            "taxes_id": [Command.clear()], "list_price": 0.0,
        })
        # Producto suelto normal: NO es composicion. Sirve para probar que
        # un ticket con un ramo y un producto suelto mueve las dos cosas.
        cls.pot = cls.env["product.product"].create({
            "name": "Maceta de barro", "tracking": "lot", "mgs_auto_lots": True,
            "is_storable": True, "available_in_pos": True,
            "taxes_id": [Command.clear()], "list_price": 6.0,
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        # mgs_check_stock exige la caja abierta. Sin esto, las pruebas de
        # contenido inválido pasarían por el error equivocado: saltaría «abre la
        # sesión de caja» en vez de la queja sobre el ramo. Quien cambia el
        # estado es set_opening_control; action_pos_session_open solo fija el
        # saldo inicial y deja la sesión en opening_control.
        cls.session.set_opening_control(0, "")
        assert cls.session.state == "opened", cls.session.state

    def receive(self, product, quantity, cost, days):
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def spec(self, *pairs):
        return json.dumps([{"product_id": product.id, "qty": qty} for product, qty in pairs])

    def sell(self, spec, price=25.0, qty=1):
        """Venta completa: albarán y coste, como haría `_process_order`."""
        order = self.order(spec, price=price, qty=qty)
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)
        return order

    def order(self, spec, price=25.0, qty=1):
        return self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": price * qty, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.bouquet.id, "qty": qty, "price_unit": price,
                "price_subtotal": price * qty, "price_subtotal_incl": price * qty,
                "mgs_bouquet_spec": spec,
            })],
        })

    # ------------------------------------------------------------------
    def test_bouquet_discounts_each_stem_and_keeps_one_ticket_line(self):
        self.receive(self.rose, 20, 2.5, 3)
        self.receive(self.green, 10, 0.4, 8)
        order = self.sell(self.spec((self.rose, 7), (self.green, 2)), price=25.0)

        # Una sola línea en el ticket, la del ramo.
        self.assertEqual(len(order.lines), 1)
        self.assertEqual(order.lines.product_id, self.bouquet)
        # Pero el stock descuenta cada tallo de su producto.
        self.assertEqual(self.rose.qty_available, 13)
        self.assertEqual(self.green.qty_available, 8)
        # Los movimientos cuelgan de la línea del ramo, con su partida asignada.
        moves = order.lines.mgs_move_ids
        self.assertEqual(len(moves), 2)
        self.assertEqual(set(moves.mapped("state")), {"done"})
        self.assertEqual(moves.move_line_ids.mapped("lot_id").mapped("product_id"),
                         self.rose | self.green)
        # El coste de la línea es el coste REAL de las flores, no el precio de venta.
        self.assertEqual(order.lines.total_cost, 7 * 2.5 + 2 * 0.4)

    def test_bouquet_takes_the_oldest_lot_first(self):
        old = self.receive(self.rose, 5, 2.0, 2)
        new = self.receive(self.rose, 5, 9.0, 30)
        order = self.sell(self.spec((self.rose, 6)))
        lines = order.lines.mgs_move_ids.move_line_ids
        # 5 de la partida que caduca antes y 1 de la siguiente.
        self.assertEqual(sum(ml.quantity for ml in lines if ml.lot_id == old), 5)
        self.assertEqual(sum(ml.quantity for ml in lines if ml.lot_id == new), 1)
        self.assertEqual(order.lines.total_cost, 5 * 2.0 + 1 * 9.0)

    def test_several_identical_bouquets_multiply_the_materials(self):
        self.receive(self.rose, 30, 1.0, 5)
        order = self.sell(self.spec((self.rose, 5)), qty=3)
        self.assertEqual(self.rose.qty_available, 15)
        self.assertEqual(order.lines.total_cost, 15 * 1.0)

    def test_stock_is_checked_against_the_flowers_before_charging(self):
        self.receive(self.rose, 3, 2.0, 5)
        lines = [{"product_id": self.bouquet.id, "qty": 1,
                  "bouquet_spec": self.spec((self.rose, 7))}]
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["pos.order"].mgs_check_stock(self.session.id, lines)
        # Con material suficiente, pasa.
        ok = [{"product_id": self.bouquet.id, "qty": 1,
               "bouquet_spec": self.spec((self.rose, 3))}]
        self.assertTrue(self.env["pos.order"].mgs_check_stock(self.session.id, ok)["ok"])

    def test_invalid_content_is_rejected_before_charging(self):
        self.receive(self.rose, 10, 2.0, 5)
        bad_specs = [
            json.dumps([{"product_id": self.rose.id, "qty": 0}]),        # cantidad cero
            json.dumps([{"product_id": self.rose.id, "qty": -3}]),       # negativa
            json.dumps([{"product_id": 999999999, "qty": 1}]),           # no existe
            json.dumps([{"product_id": self.bouquet.id, "qty": 1}]),     # ramo dentro de ramo
            json.dumps([]),                                              # vacío
            "esto no es json",
        ]
        for spec in bad_specs:
            lines = [{"product_id": self.bouquet.id, "qty": 1, "bouquet_spec": spec}]
            with self.assertRaises(UserError), self.env.cr.savepoint():
                self.env["pos.order"].mgs_check_stock(self.session.id, lines)
            with self.assertRaises(UserError), self.env.cr.savepoint():
                self.order(spec)
        self.assertEqual(self.rose.qty_available, 10)

    def test_a_normal_product_cannot_carry_materials(self):
        self.receive(self.rose, 10, 2.0, 5)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["pos.order"].create({
                "session_id": self.session.id, "amount_tax": 0, "amount_total": 5,
                "amount_paid": 0, "amount_return": 0,
                "lines": [Command.create({
                    "product_id": self.rose.id, "qty": 1, "price_unit": 5,
                    "price_subtotal": 5, "price_subtotal_incl": 5,
                    "mgs_bouquet_spec": self.spec((self.green, 1)),
                })],
            })

    def test_a_composition_cannot_hold_its_own_stock(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["product.product"].create({
                "name": "Ramo imposible", "mgs_is_composition": True, "is_storable": True,
            })

    def test_sold_content_is_frozen(self):
        self.receive(self.rose, 10, 2.0, 5)
        order = self.sell(self.spec((self.rose, 2)))
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.lines.write({"mgs_bouquet_spec": self.spec((self.rose, 99))})
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            order.lines.mgs_bouquet_ids.write({"quantity": 99})
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login="bouquet_staff", groups="mi_gestor_stock.group_mgs_user",
            company_id=self.env.company.id)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["mgs.bouquet.component"].with_user(staff).create({
                "line_id": order.lines.id, "product_id": self.rose.id, "quantity": 1})

    def test_expired_flowers_are_not_used_in_a_bouquet(self):
        self.receive(self.rose, 5, 2.0, -1)  # ya caducada
        lines = [{"product_id": self.bouquet.id, "qty": 1,
                  "bouquet_spec": self.spec((self.rose, 2))}]
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["pos.order"].mgs_check_stock(self.session.id, lines)
    def test_a_ticket_with_a_bouquet_and_a_loose_product_moves_both(self):
        """Fija que la convivencia de los dos overrides de
        _create_move_from_pos_order_lines (mgs_bouquet.py y mgs_pos_stock.py)
        no se pisa. Hoy solo funciona porque mgs_bouquet se importa DESPUES de
        mgs_pos_stock en models/__init__.py (ver el comentario junto a ese
        import); si alguna vez uno de los dos deja de llamar a super() para lo
        que no es suyo, esta prueba lo nota."""
        self.receive(self.rose, 20, 2.5, 3)
        self.receive(self.green, 10, 0.4, 8)
        self.receive(self.pot, 5, 3.0, 30)
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 25.0 + 2 * 6.0, "amount_paid": 0, "amount_return": 0,
            "lines": [
                Command.create({
                    "product_id": self.bouquet.id, "qty": 1, "price_unit": 25.0,
                    "price_subtotal": 25.0, "price_subtotal_incl": 25.0,
                    "mgs_bouquet_spec": self.spec((self.rose, 7), (self.green, 2)),
                }),
                Command.create({
                    "product_id": self.pot.id, "qty": 2, "price_unit": 6.0,
                    "price_subtotal": 12.0, "price_subtotal_incl": 12.0,
                }),
            ],
        })
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)

        # Las flores del ramo SI se descuentan...
        self.assertEqual(self.rose.qty_available, 13)
        self.assertEqual(self.green.qty_available, 8)
        # ...Y el producto suelto TAMBIEN, no solo uno de los dos.
        self.assertEqual(self.pot.qty_available, 3)

        bouquet_line = order.lines.filtered(lambda l: l.product_id == self.bouquet)
        pot_line = order.lines.filtered(lambda l: l.product_id == self.pot)
        self.assertEqual(len(bouquet_line.mgs_move_ids), 2)
        self.assertEqual(len(pot_line.mgs_move_ids), 1)
        self.assertEqual(bouquet_line.total_cost, 7 * 2.5 + 2 * 0.4)
        self.assertEqual(pot_line.total_cost, 2 * 3.0)

    def test_returning_a_bouquet_refunds_the_money_but_not_the_flowers(self):
        """EVENTOS.md: devolver un ramo devuelve el dinero, pero las flores ya
        estan cortadas y montadas, asi que NO vuelven al stock. No es un
        fallo: es la decision documentada. Esta prueba la fija para que nadie
        la "arregle" sin darse cuenta de por que existe."""
        self.receive(self.rose, 20, 2.5, 3)
        self.receive(self.green, 10, 0.4, 8)
        order = self.sell(self.spec((self.rose, 7), (self.green, 2)), price=25.0)
        self.assertEqual(self.rose.qty_available, 13)
        self.assertEqual(self.green.qty_available, 8)

        refund = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": -25.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.bouquet.id, "qty": -1, "price_unit": 25.0,
                "price_subtotal": -25.0, "price_subtotal_incl": -25.0,
                "refunded_orderline_id": order.lines.id,
            })],
        })
        refund._create_order_picking()

        # El dinero SI vuelve...
        self.assertEqual(refund.amount_total, -25.0)
        # ...pero las flores NO: ya estan cortadas y montadas en el ramo vendido.
        self.assertEqual(self.rose.qty_available, 13)
        self.assertEqual(self.green.qty_available, 8)
        self.assertFalse(refund.lines.mgs_move_ids)
