from datetime import datetime, timedelta
from uuid import uuid4

import pytz

from odoo import Command, fields
from odoo.tests import tagged, new_test_user, TransactionCase
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon

MADRID = pytz.timezone("Europe/Madrid")


@tagged("post_install", "-at_install")
class TestStockLedgerPos(TestPointOfSaleCommon):
    """Entradas y salidas (plan «Correcciones de ventas», #6): la vista
    `mgs.stock.ledger` no crea ningún registro nuevo, solo lee movimientos ya
    confirmados. Aquí se cubren recepción, venta suelta, componente de ramo,
    merma y devolución; los movimientos de evento se prueban aparte en
    TestStockLedgerEvent (necesitan base.main_company, ver test_consumption.py)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa entradas y salidas", "tracking": "lot", "mgs_auto_lots": True,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
        })
        cls.bouquet = cls.env["product.product"].create({
            "name": "Ramo entradas y salidas", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "available_in_pos": True,
            "taxes_id": [Command.clear()], "list_price": 0.0,
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.session.set_opening_control(0, "")
        cls.Ledger = cls.env["mgs.stock.ledger"]

    def receive(self, quantity, cost, days=10, product=None):
        product = product or self.rose
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def ledger_data(self, **kwargs):
        return self.Ledger.mgs_ledger_data(**kwargs)

    def rows_for(self, motivo, data=None):
        data = data or self.ledger_data()
        return [row for row in data["rows"] if row["motivo"] == motivo]

    # ------------------------------------------------------------------
    def test_ledger_includes_reception_as_entrada(self):
        self.receive(10, 2.0)
        rows = self.rows_for("reception")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "in")
        self.assertEqual(rows[0]["quantity"], 10)
        self.assertEqual(rows[0]["product_id"][0], self.rose.id)

    def test_ledger_includes_pos_sale_as_salida_with_reason(self):
        self.receive(10, 2.0)
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 40.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.rose.id, "qty": 4, "price_unit": 10,
                "price_subtotal": 40, "price_subtotal_incl": 40,
            })],
        })
        order._create_order_picking()
        rows = self.rows_for("pos")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "out")
        self.assertEqual(rows[0]["quantity"], 4)

    def test_ledger_includes_bouquet_component_as_salida(self):
        import json
        self.receive(10, 2.0)
        spec = json.dumps([{"product_id": self.rose.id, "qty": 5}])
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 25.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.bouquet.id, "qty": 1, "price_unit": 25.0,
                "price_subtotal": 25.0, "price_subtotal_incl": 25.0,
                "mgs_bouquet_spec": spec,
            })],
        })
        order._create_order_picking()
        rows = self.rows_for("bouquet")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 5)
        # No debe aparecer también como "pos": ni el ramo (no almacenable) ni
        # sus componentes se cuentan dos veces.
        self.assertFalse(self.rows_for("pos"))

    def test_ledger_includes_scrap_with_reason_label(self):
        lot = self.receive(10, 2.0)
        location = self.pos_config.picking_type_id.default_location_src_id
        scrap = self.env["stock.scrap"].create({
            "product_id": self.rose.id, "scrap_qty": 2, "lot_id": lot.id,
            "location_id": location.id, "mgs_reason": "expiry",
        })
        scrap.do_scrap()
        rows = self.rows_for("scrap_expiry")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "out")
        self.assertEqual(rows[0]["quantity"], 2)
        self.assertEqual(rows[0]["motivo_label"], "Merma: caducidad")

    def test_ledger_includes_return_as_entrada(self):
        self.receive(10, 2.0)
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 20.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.rose.id, "qty": 2, "price_unit": 10,
                "price_subtotal": 20, "price_subtotal_incl": 20,
            })],
        })
        order._create_order_picking()
        refund = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": -10.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.rose.id, "qty": -1, "price_unit": 10,
                "price_subtotal": -10, "price_subtotal_incl": -10,
                "refunded_orderline_id": order.lines.id,
            })],
        })
        refund._create_order_picking()
        rows = self.rows_for("return")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "in")
        self.assertEqual(rows[0]["quantity"], 1)

    def test_ledger_no_duplicate_rows_for_bouquet_vs_component(self):
        import json
        self.receive(10, 2.0)
        spec = json.dumps([{"product_id": self.rose.id, "qty": 3}])
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 25.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.bouquet.id, "qty": 1, "price_unit": 25.0,
                "price_subtotal": 25.0, "price_subtotal_incl": 25.0,
                "mgs_bouquet_spec": spec,
            })],
        })
        order._create_order_picking()
        data = self.ledger_data(direction="out")
        # Solo la salida de la rosa (componente): el ramo no es almacenable,
        # así que no genera un movimiento de stock propio.
        self.assertEqual(len(data["rows"]), 1)

    def test_ledger_cost_hidden_for_staff_group(self):
        self.receive(10, 2.0)
        staff = new_test_user(
            self.env(context=dict(self.env.context, no_reset_password=True)),
            login="mgs_ledger_staff", groups="mi_gestor_stock.group_mgs_user",
            company_id=self.env.company.id)
        data = self.Ledger.with_user(staff).mgs_ledger_data()
        self.assertFalse(data["can_see_cost"])
        self.assertTrue(all("cost" not in row for row in data["rows"]))
        manager_data = self.ledger_data()
        self.assertTrue(manager_data["can_see_cost"])
        self.assertTrue(all("cost" in row for row in manager_data["rows"]))

    def test_ledger_product_filter(self):
        self.receive(5, 2.0)
        other = self.env["product.product"].create({
            "name": "Otro producto entradas y salidas", "tracking": "lot",
            "mgs_auto_lots": True, "is_storable": True, "taxes_id": [Command.clear()],
        })
        self.receive(3, 1.0, product=other)
        data = self.ledger_data(product_query="Rosa entradas")
        self.assertTrue(all(row["product_id"][0] == self.rose.id for row in data["rows"]))
        self.assertTrue(data["rows"])

    def test_ledger_default_period_is_current_month_madrid_tz(self):
        data = self.ledger_data()
        today = datetime.now(MADRID).date()
        self.assertEqual(data["date_from"], fields.Date.to_string(today.replace(day=1)))
        self.assertEqual(fields.Date.from_string(data["date_to"]).month, today.month)


@tagged("post_install", "-at_install")
class TestStockLedgerEvent(TransactionCase):
    """Movimientos de evento: base.main_company, igual que
    TestConsumptionEvent en test_consumption.py (la ubicación de tránsito de
    alquiler está fija a esa compañía)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.customer = cls.env["res.partner"].create({"name": "Novia entradas y salidas"})
        cls.arch = cls.env["product.product"].create({
            "name": "Arco entradas y salidas", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "mgs_rental_ok": True, "list_price": 100.0,
        })
        cls.centre = cls.env["product.product"].create({
            "name": "Centro entradas y salidas", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "list_price": 25.0,
        })
        cls.today = datetime.now(MADRID).date()
        cls.Ledger = cls.env["mgs.stock.ledger"]

    def stock(self, product, quantity, cost=10.0):
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
        })]}).action_confirm()

    def event(self, lines, days=0, length=1):
        start = self.today + timedelta(days=days)
        return self.env["mgs.event"].create({
            "partner_id": self.customer.id,
            "event_date": start, "return_date": start + timedelta(days=length),
            "line_ids": lines,
        })

    def test_ledger_includes_event_movement_for_rental(self):
        self.stock(self.arch, 5, cost=40.0)
        event = self.event([Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 1, "unit_price": 100.0})])
        event.action_confirm()
        event.action_deliver()
        data = self.Ledger.mgs_ledger_data(
            date_from=fields.Date.to_string(self.today), date_to=fields.Date.to_string(self.today))
        # self.stock() ya deja su propia fila de "reception" para el mismo
        # producto el mismo día: se acota por motivo para quedarse solo con
        # el movimiento del evento.
        rows = [row for row in data["rows"]
                if row["product_id"][0] == self.arch.id and row["motivo"] == "event"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "out")

    def test_ledger_includes_sold_event_line_as_venta_evento(self):
        self.stock(self.centre, 10, cost=8.0)
        event = self.event([Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 4, "unit_price": 25.0})])
        event.action_confirm()
        event.action_deliver()
        data = self.Ledger.mgs_ledger_data(
            date_from=fields.Date.to_string(self.today), date_to=fields.Date.to_string(self.today))
        rows = [row for row in data["rows"]
                if row["product_id"][0] == self.centre.id and row["motivo"] == "event"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "out")
        self.assertEqual(rows[0]["quantity"], 4)
