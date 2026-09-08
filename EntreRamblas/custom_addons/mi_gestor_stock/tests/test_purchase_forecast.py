from datetime import date, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged("post_install", "-at_install")
class TestPurchaseForecast(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env["res.partner"].create({"name": "Mayorista habitual"})
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa de previsión", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "use_expiration_date": True, "standard_price": 1.0,
        })
        cls.customer = cls.env["res.partner"].create({"name": "Cliente de previsión"})

    def receive(self, quantity, cost=1.5):
        wizard = self.env["mgs.reception"].create({
            "supplier_id": self.supplier.id,
            "line_ids": [Command.create({
                "product_id": self.rose.id, "quantity": quantity, "unit_cost": cost,
                "expiry_date": fields.Date.today() + timedelta(days=30),
            })],
        })
        wizard.action_confirm()
        return wizard.picking_id.move_ids

    def sell_and_backdate(self, quantity, event_date):
        """Vende (por un evento, más simple que montar sesión de TPV) y
        retrasa la fecha del movimiento a otro año, simulando consumo real
        de una campaña pasada."""
        event = self.env["mgs.event"].create({
            "partner_id": self.customer.id,
            "event_date": event_date, "return_date": event_date + timedelta(days=1),
            "line_ids": [Command.create({
                "product_id": self.rose.id, "is_rental": False,
                "quantity": quantity, "unit_price": 3.0})],
        })
        event.action_confirm()
        event.action_deliver()
        moves = event.move_ids.filtered(lambda m: m.product_id == self.rose)
        # Madrid a mediodia de esa fecha, en UTC naive, para que caiga dentro
        # de la ventana de consulta de _mgs_madrid_range sin ambigüedad de DST.
        moves.write({"date": fields.Datetime.to_datetime("%s 12:00:00" % event_date)})
        return moves

    def forecast(self, **vals):
        return self.env["mgs.purchase.forecast"].create(dict({
            "campaign": "valentine", "years_back": 2, "safety_factor": 1.15,
        }, **vals))

    # ------------------------------------------------------------------
    def test_no_history_still_computes_against_current_stock(self):
        self.receive(5)
        wiz = self.forecast()
        wiz.action_compute()
        self.assertFalse(wiz.has_history)
        self.assertFalse(wiz.line_ids)  # sin historial, no hay nada que proponer

    def test_proposes_the_historical_max_with_safety_margin_minus_stock(self):
        last_year = date.today().year - 1
        self.receive(40)
        self.sell_and_backdate(40, date(last_year, 2, 10))
        two_years_ago = date.today().year - 2
        self.receive(60)
        self.sell_and_backdate(60, date(two_years_ago, 2, 12))
        self.receive(20, cost=1.5)  # ya hay 20 en la tienda

        wiz = self.forecast(years_back=2, safety_factor=1.15)
        wiz.action_compute()
        self.assertTrue(wiz.has_history)
        line = wiz.line_ids
        self.assertEqual(line.product_id, self.rose)
        self.assertEqual(line.max_qty, 60)
        self.assertEqual(line.usable_qty, 20)
        self.assertAlmostEqual(line.proposed_qty, 60 * 1.15 - 20, places=2)
        self.assertEqual(line.supplier_id, self.supplier)

    def test_sales_outside_the_campaign_window_do_not_count(self):
        last_year = date.today().year - 1
        self.receive(50)
        self.sell_and_backdate(50, date(last_year, 6, 15))  # en junio, no San Valentín
        wiz = self.forecast()
        wiz.action_compute()
        self.assertFalse(wiz.has_history)

    def test_create_purchase_order_groups_by_usual_supplier(self):
        last_year = date.today().year - 1
        self.receive(40)
        self.sell_and_backdate(40, date(last_year, 2, 10))
        wiz = self.forecast()
        wiz.action_compute()
        result = wiz.action_create_purchase_order()
        orders = self.env["mgs.purchase.order"].search(result["domain"])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.partner_id, self.supplier)
        self.assertEqual(orders.state, "draft")
        self.assertEqual(orders.line_ids.product_id, self.rose)

    def test_product_without_a_known_supplier_is_left_out_but_does_not_block_the_rest(self):
        green = self.env["product.product"].create({
            "name": "Eucalipto sin proveedor conocido", "is_storable": True,
            "tracking": "lot", "mgs_auto_lots": True, "use_expiration_date": True,
        })
        last_year = date.today().year - 1
        self.receive(40)
        self.sell_and_backdate(40, date(last_year, 2, 10))
        # eucalipto: se recibe con mgs.reception pero luego se le borra el
        # rastro de proveedor a mano, para simular una partida sin proveedor
        # conocido en ninguna parte.
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": green.id, "quantity": 30, "unit_cost": 1.0,
        })]})
        wizard.action_confirm()
        event = self.env["mgs.event"].create({
            "partner_id": self.customer.id,
            "event_date": date(last_year, 2, 10), "return_date": date(last_year, 2, 11),
            "line_ids": [Command.create({
                "product_id": green.id, "is_rental": False,
                "quantity": 10, "unit_price": 1.0})],
        })
        event.action_confirm()
        event.action_deliver()
        event.move_ids.filtered(lambda m: m.product_id == green).write(
            {"date": fields.Datetime.to_datetime("%s 12:00:00" % date(last_year, 2, 10))})
        # Borra el rastro de proveedor de esa partida para forzar "sin conocido".
        self.env.cr.execute("UPDATE stock_lot SET mgs_supplier_id = NULL WHERE product_id = %s", [green.id])

        wiz = self.forecast()
        wiz.action_compute()
        result = wiz.action_create_purchase_order()
        orders = self.env["mgs.purchase.order"].search(result["domain"])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.line_ids.product_id, self.rose)  # el eucalipto se queda fuera

    def test_nothing_to_order_raises_a_clear_error(self):
        self.receive(1000)  # tanto stock que no hace falta pedir nada
        last_year = date.today().year - 1
        self.sell_and_backdate(5, date(last_year, 2, 10))
        wiz = self.forecast()
        wiz.action_compute()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            wiz.action_create_purchase_order()

    def test_custom_dates_use_a_single_window_not_years_back(self):
        wiz = self.forecast(campaign="custom",
                            date_from=date(2020, 1, 1), date_to=date(2020, 1, 31))
        wiz.action_compute()  # no debe fallar ni iterar varios años
        self.assertFalse(wiz.line_ids)

    def test_custom_requires_both_dates(self):
        wiz = self.forecast(campaign="custom", date_from=False, date_to=False)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            wiz.action_compute()

    def test_only_the_owner_runs_the_forecast(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login="forecast_staff", groups="mi_gestor_stock.group_mgs_user")
        wiz = self.forecast()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            wiz.with_user(staff).action_compute()
