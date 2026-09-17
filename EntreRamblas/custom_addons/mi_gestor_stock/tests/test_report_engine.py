# -*- coding: utf-8 -*-
"""Motor de informes personalizados: comprobación cruzada contra el informe
mensual heredado (misma base de datos, dos implementaciones independientes
deben coincidir) y comportamiento propio de las secciones nuevas
(devoluciones sin netear, agrupación, orden)."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytz

from odoo import Command
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon

from ..models import mgs_report_engine as engine


@tagged("post_install", "-at_install")
class TestReportEngineMatchesLegacy(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.report_category = cls.env["product.category"].create({"name": "Prueba motor de informes"})
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa motor", "tracking": "lot", "mgs_auto_lots": True,
            "categ_id": cls.report_category.id,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.today = datetime.now(pytz.timezone("Europe/Madrid")).date()

    def receive(self, quantity, cost, days=30):
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.flower.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": self.today + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def order(self, quantity, original=False):
        return self.env["pos.order"].create({
            "uuid": str(uuid4()),
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": quantity * 10, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.flower.id, "qty": quantity, "price_unit": 10,
                "price_subtotal": quantity * 10, "price_subtotal_incl": quantity * 10,
                "refunded_orderline_id": original.id if original else False,
            })],
        })

    def fixture(self):
        """Una venta de 7, una devolución parcial de 3 y una merma: mismos
        datos que ejercitan resumen/ventas/devoluciones/mermas/stock."""
        self.receive(10, 2)
        order = self.order(7)
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)
        order.state = "paid"
        refund = self.order(-3, order.lines)
        refund._create_order_picking()
        refund.lines._compute_total_cost(refund.picking_ids.move_ids)
        refund.state = "paid"
        scrap = self.env["stock.scrap"].create({
            "product_id": self.flower.id,
            "lot_id": refund.picking_ids.move_line_ids.lot_id.id, "scrap_qty": 1,
            "location_id": self.pos_config.picking_type_id.default_location_src_id.id,
            "mgs_reason": "deterioration",
        })
        scrap.do_scrap()
        return order, refund

    def build_no_filter(self):
        template = self.env["mgs.report.template"].create({
            "name": "Comprobación cruzada", "date_from": self.today, "date_to": self.today,
        })
        return engine.build(template)

    def legacy_data(self):
        report = self.env["mgs.monthly.report"].create({
            "date_from": self.today, "date_to": self.today,
            "category_id": self.report_category.id,
        })
        return report.mgs_get_report_data()

    # ------------------------------------------------------------------
    def test_totals_match_the_legacy_monthly_report(self):
        self.fixture()
        legacy = self.legacy_data()
        built = self.build_no_filter()
        resumen = built["resumen"]
        self.assertEqual(resumen["total_revenue"], legacy["total_revenue"])
        self.assertEqual(resumen["total_cost_sold"], legacy["total_cost_sold"])
        self.assertEqual(resumen["gross_profit"], legacy["gross_profit"])
        self.assertEqual(resumen["gross_sales_including_tax"], legacy["gross_sales_including_tax"])
        self.assertEqual(resumen["refunds_including_tax"], legacy["refunds_including_tax"])
        self.assertEqual(resumen["sale_ticket_count"], legacy["sale_ticket_count"])
        self.assertEqual(resumen["refund_ticket_count"], legacy["refund_ticket_count"])
        self.assertEqual(sum(row["cost"] for row in built["mermas"]), legacy["scrap_cost"])
        self.assertEqual(built["stock_value"], legacy["stock_value"])

    def test_ventas_and_devoluciones_are_reported_separately_not_netted(self):
        order, refund = self.fixture()
        built = self.build_no_filter()
        self.assertEqual(len(built["ventas"]), 1)
        self.assertEqual(built["ventas"][0]["qty"], 7)
        self.assertEqual(len(built["devoluciones"]), 1)
        row = built["devoluciones"][0]
        self.assertEqual(row["qty"], 3)
        self.assertEqual(row["original_order"], order.name)
        self.assertEqual(row["return_order"], refund.name)

    def test_group_by_product_and_order_by_amount(self):
        self.receive(10, 2)
        # Servicio, no almacenable: solo hace falta que exista como línea de
        # venta para agrupar por producto, no que tenga existencias reales.
        other = self.env["product.product"].create({
            "name": "Tulipán motor", "categ_id": self.report_category.id,
            "type": "service", "taxes_id": [Command.clear()],
        })
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 90, "amount_paid": 0, "amount_return": 0,
            "lines": [
                Command.create({"product_id": self.flower.id, "qty": 7, "price_unit": 10,
                                "price_subtotal": 70, "price_subtotal_incl": 70}),
                Command.create({"product_id": other.id, "qty": 2, "price_unit": 10,
                                "price_subtotal": 20, "price_subtotal_incl": 20}),
            ],
        })
        order._create_order_picking()
        order.state = "paid"
        template = self.env["mgs.report.template"].create({
            "name": "Agrupado por producto", "date_from": self.today, "date_to": self.today,
            "group_by": "product", "order_by": "amount_desc",
        })
        built = engine.build(template)
        self.assertEqual(len(built["ventas"]), 2)
        self.assertEqual(built["ventas"][0]["amount"], 70)
        self.assertEqual(built["ventas"][1]["amount"], 20)

    def test_correcciones_section_is_empty_before_phase_5(self):
        # TODO: cuando models/mgs_correction.py exista (Fase 5), sustituir por
        # una comprobación real con correcciones creadas en la BD.
        built = self.build_no_filter()
        self.assertEqual(built["correcciones"], [])
