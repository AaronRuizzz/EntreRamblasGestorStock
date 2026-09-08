import json
from datetime import datetime, timedelta

import pytz

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestConsumptionPos(TestPointOfSaleCommon):
    """Ventas sueltas y ramos, dentro del TPV. Usa TestPointOfSaleCommon, que
    monta su propia compañía de pruebas (no base.main_company) — por eso las
    pruebas que tocan eventos y alquiler viven aparte, en TestConsumptionEvent:
    la ubicación de tránsito del alquiler está fija a base.main_company (ver
    data/mgs_event_data.xml), y mezclar las dos aquí sería un lío de
    multiempresa que no existe en la tienda real (una sola compañía)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa de consumo", "tracking": "lot", "mgs_auto_lots": True,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
            "list_price": 2.0,
        })
        cls.bouquet = cls.env["product.product"].create({
            "name": "Ramo de consumo", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "available_in_pos": True,
            "taxes_id": [Command.clear()], "list_price": 0.0,
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.session.set_opening_control(0, "")
        assert cls.session.state == "opened", cls.session.state

    def receive(self, product, quantity, cost=2.0, days=10):
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def sell_loose(self, product, quantity, price):
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": price * quantity, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": product.id, "qty": quantity, "price_unit": price,
                "price_subtotal": price * quantity, "price_subtotal_incl": price * quantity,
            })],
        })
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)
        return order

    def sell_bouquet(self, roses_qty, price=30.0):
        spec = json.dumps([{"product_id": self.rose.id, "qty": roses_qty}])
        order = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": price, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.bouquet.id, "qty": 1, "price_unit": price,
                "price_subtotal": price, "price_subtotal_incl": price,
                "mgs_bouquet_spec": spec,
            })],
        })
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)
        return order

    def consumption_for(self, product):
        return self.env["mgs.flower.consumption"].search([("product_id", "=", product.id)])

    # ------------------------------------------------------------------
    def test_loose_and_bouquet_sales_add_up_to_the_real_total(self):
        """3 rosas sueltas + un ramo de 12 => 15 rosas de consumo, no «3
        rosas + 1 ramo a medida»."""
        self.receive(self.rose, 100, cost=2.0)
        self.sell_loose(self.rose, 3, price=2.5)
        self.sell_bouquet(12)

        rows = self.consumption_for(self.rose)
        self.assertEqual(sum(rows.mapped("quantity")), 15)
        self.assertEqual(sum(rows.mapped("cost")), 15 * 2.0)
        self.assertEqual(set(rows.mapped("origin")), {"pos", "bouquet"})

    def test_returning_a_bouquet_leaves_no_consumption_trace(self):
        """La devolución de un ramo no reingresa las flores (EVENTOS.md); por
        la misma razón, tampoco debe generar una fila de consumo nueva."""
        self.receive(self.rose, 20, cost=2.0)
        order = self.sell_bouquet(7)
        before = len(self.consumption_for(self.rose))

        refund = self.env["pos.order"].create({
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": -30.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.bouquet.id, "qty": -1, "price_unit": 30.0,
                "price_subtotal": -30.0, "price_subtotal_incl": -30.0,
                "refunded_orderline_id": order.lines.id,
            })],
        })
        refund._create_order_picking()
        self.assertEqual(len(self.consumption_for(self.rose)), before)


@tagged("post_install", "-at_install")
class TestConsumptionEvent(TransactionCase):
    """Eventos y encargos. TransactionCase liso, como test_event.py: opera en
    base.main_company sin la compañía de pruebas propia de TestPointOfSaleCommon,
    que es donde vive la ubicación de tránsito del alquiler."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Novia de consumo"})
        cls.arch = cls.env["product.product"].create({
            "name": "Arco de consumo", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "mgs_rental_ok": True, "list_price": 100.0,
        })
        cls.centre = cls.env["product.product"].create({
            "name": "Centro de consumo", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "list_price": 25.0,
        })
        # Día de Madrid, no de UTC (ver mgs_monthly_report._mgs_period): cerca
        # de la medianoche española un cobro fechado "ahora mismo" quedaría
        # fuera de la ventana del informe si aquí se usara fields.Date.today().
        cls.today = datetime.now(pytz.timezone("Europe/Madrid")).date()

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

    def consumption_for(self, product):
        return self.env["mgs.flower.consumption"].search([("product_id", "=", product.id)])

    # ------------------------------------------------------------------
    def test_rental_delivery_is_not_consumption(self):
        """Un arco alquilado vuelve: no se «consume», va a tránsito, no a
        cliente. No debe aparecer aquí."""
        self.stock(self.arch, 5, cost=40.0)
        event = self.event([Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 1, "unit_price": 100.0})])
        event.action_confirm()
        event.action_deliver()
        self.assertFalse(self.consumption_for(self.arch))

    def test_sold_event_line_is_consumption_but_not_summed_twice_in_revenue(self):
        """Un centro de mesa vendido en un evento SÍ es consumo (se va de la
        tienda de verdad), y el informe mensual lo separa de las ventas de
        mostrador sin sumarlo a total_revenue (mismo criterio que ya usa
        _mgs_event_data con el dinero del evento)."""
        self.stock(self.centre, 10, cost=8.0)
        event = self.event([Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 4, "unit_price": 25.0})])
        event.action_confirm()
        event.action_deliver()
        rows = self.consumption_for(self.centre)
        self.assertEqual(sum(rows.mapped("quantity")), 4)
        self.assertEqual(sum(rows.mapped("cost")), 4 * 8.0)
        self.assertEqual(set(rows.mapped("origin")), {"event"})

        report = self.env["mgs.monthly.report"].create({
            "date_from": self.today, "date_to": self.today})
        data = report.mgs_get_report_data()
        self.assertEqual(data["total_revenue"], 0.0)  # nada pasó por el TPV
        row = next(r for r in data["consumption_rows"] if r["name"] == self.centre.display_name)
        self.assertEqual(row["qty"], 4)
        self.assertEqual(row["cost"], 4 * 8.0)

    def test_monthly_report_zip_and_pdf_include_the_consumption_table(self):
        self.stock(self.centre, 10, cost=8.0)
        event = self.event([Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 2, "unit_price": 25.0})])
        event.action_confirm()
        event.action_deliver()
        report = self.env["mgs.monthly.report"].create({
            "date_from": self.today, "date_to": self.today})
        report.action_export_all_csv()
        self.assertTrue(report.export_file)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mi_gestor_stock.action_report_mgs_monthly", report.ids)[0].decode()
        self.assertIn("Consumo de flor", html)
