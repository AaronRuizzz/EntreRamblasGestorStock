# -*- coding: utf-8 -*-
from datetime import datetime
from uuid import uuid4

import pytz

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon

from ..models import mgs_report_engine as engine


@tagged("post_install", "-at_install")
class TestReportExclusion(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa clasificable", "type": "service", "taxes_id": [Command.clear()],
        })
        cls.lily = cls.env["product.product"].create({
            "name": "Lirio clasificable", "type": "service", "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.today = datetime.now(pytz.timezone("Europe/Madrid")).date()

    def sale(self, lines, refund_of=False):
        amount = sum(quantity * price for product, quantity, price in lines)
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id, "amount_tax": 0,
            "amount_total": amount, "amount_paid": amount, "amount_return": 0,
            "lines": [Command.create({
                "product_id": product.id, "qty": quantity, "price_unit": price,
                "price_subtotal": quantity * price, "price_subtotal_incl": quantity * price,
                "refunded_orderline_id": refund_of.id if refund_of else False,
            }) for product, quantity, price in lines],
        })
        order.state = "paid"
        return order

    def template(self):
        return self.env["mgs.report.template"].create({
            "name": "Revisión", "date_from": self.today, "date_to": self.today,
        })

    def test_marking_a_line_excludes_it_but_never_changes_the_sale(self):
        order = self.sale([(self.rose, 1, 10), (self.lily, 1, 20)])
        self.env["pos.payment"].create({
            "pos_order_id": order.id, "payment_method_id": self.cash_payment_method.id, "amount": 30,
        })
        line = order.lines.filtered(lambda item: item.product_id == self.rose)
        line.with_context(mgs_report_exclusion_change=True).action_mgs_set_report_exclusion(
            True, "Prueba de clasificación")
        line.invalidate_recordset()
        self.assertTrue(line.mgs_report_excluded)
        self.assertEqual(order.amount_total, 30)
        self.assertEqual(order.lines.mapped("qty"), [1, 1])
        data = engine.build(self.template())
        self.assertEqual(sum(row["amount"] for row in data["ventas"]), 20)
        self.assertEqual(data["cobros"][0]["received"], 20)
        log = self.env["mgs.report.exclusion.log"].search([("line_id", "=", line.id)])
        self.assertEqual(len(log), 1)
        self.assertTrue(log.is_excluded)
        with self.assertRaises(AccessError):
            log.write({"reason": "No"})

    def test_refund_inherits_the_original_line_classification(self):
        sale = self.sale([(self.rose, 1, 10)])
        sale.lines.action_mgs_set_report_exclusion(True, "Prueba")
        refund = self.sale([(self.rose, -1, 10)], refund_of=sale.lines)
        self.assertTrue(refund.lines.mgs_report_excluded)
        data = engine.build(self.template())
        self.assertFalse(data["ventas"])
        self.assertFalse(data["devoluciones"])
        sale.lines.action_mgs_set_report_exclusion(False, "Se reincorpora")
        refund.lines.invalidate_recordset(["mgs_report_excluded"])
        self.assertFalse(refund.lines.mgs_report_excluded)

    def test_review_rows_are_built_and_require_a_reason(self):
        self.sale([(self.rose, 1, 10)])
        template = self.template()
        template.action_refresh_preview()
        self.assertEqual(len(template.review_line_ids), 1)
        wizard = self.env["mgs.report.exclusion.wizard"].create({
            "review_ids": [(6, 0, template.review_line_ids.ids)], "excluded": True, "reason": "  ",
        })
        with self.assertRaises(UserError):
            wizard.action_confirm()
