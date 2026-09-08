# -*- coding: utf-8 -*-
"""Avisos de stock (models/mgs_stock_alert.py): el cron de los avisos
periódicos (_mgs_cron_run_alerts / _mgs_next_due) no se ejercitaba todavía."""
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestStockAlertNextDue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Rosa de aviso", "is_storable": True,
        })

    def alert(self, **vals):
        return self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "periodic",
            **vals,
        })

    def test_next_due_is_now_when_it_never_ran(self):
        alert = self.alert(interval_type="weekly")
        self.assertFalse(alert.last_run)
        self.assertLessEqual(alert._mgs_next_due(), fields.Datetime.now())

    def test_next_due_weekly_adds_one_week_to_the_last_run(self):
        last_run = fields.Datetime.now() - timedelta(days=1)
        alert = self.alert(interval_type="weekly", last_run=last_run)
        self.assertEqual(alert._mgs_next_due(), last_run + timedelta(weeks=1))

    def test_next_due_monthly_adds_one_month_to_the_last_run(self):
        last_run = fields.Datetime.to_datetime("2026-01-15 10:00:00")
        alert = self.alert(interval_type="monthly", last_run=last_run)
        self.assertEqual(alert._mgs_next_due(), fields.Datetime.to_datetime("2026-02-15 10:00:00"))

    def test_next_due_in_days_adds_the_configured_number_of_days(self):
        last_run = fields.Datetime.now() - timedelta(days=1)
        alert = self.alert(interval_type="days", interval_number=3, last_run=last_run)
        self.assertEqual(alert._mgs_next_due(), last_run + timedelta(days=3))

    def test_next_due_in_days_treats_less_than_one_day_as_one(self):
        # _check_interval_number ya exige >= 1 al guardar, pero _mgs_next_due
        # no debe generar un intervalo de cero o negativo si algo lo saltara.
        last_run = fields.Datetime.now() - timedelta(days=1)
        alert = self.alert(interval_type="days", interval_number=1, last_run=last_run)
        self.assertEqual(alert._mgs_next_due(), last_run + timedelta(days=1))

    def test_a_periodic_alert_with_less_than_one_day_is_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.alert(interval_type="days", interval_number=0)


@tagged("post_install", "-at_install")
class TestStockAlertCron(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Gerbera de aviso", "is_storable": True,
        })

    def stock(self, quantity, cost=5.0):
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.product.id, "quantity": quantity, "unit_cost": cost,
        })]}).action_confirm()

    def test_cron_creates_a_notice_and_stamps_last_run_when_an_alert_is_due(self):
        self.stock(8)
        alert = self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "periodic",
            "interval_type": "weekly",
        })
        self.assertFalse(alert.last_run)
        self.env["mgs.stock.alert"]._mgs_cron_run_alerts()
        self.assertTrue(alert.last_run)
        notice = self.env["mgs.stock.alert.notice"].search([("alert_id", "=", alert.id)])
        self.assertEqual(len(notice), 1)
        self.assertEqual(notice.product_id, self.product.product_tmpl_id)
        self.assertIn("8", notice.name)
        self.assertFalse(notice.is_read)

    def test_cron_leaves_an_alert_that_is_not_due_yet_untouched(self):
        alert = self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "periodic",
            "interval_type": "weekly", "last_run": fields.Datetime.now(),
        })
        self.env["mgs.stock.alert"]._mgs_cron_run_alerts()
        self.assertFalse(self.env["mgs.stock.alert.notice"].search([("alert_id", "=", alert.id)]))

    def test_cron_ignores_threshold_alerts_entirely(self):
        # Los de umbral se calculan en vivo (is_triggered); el cron es solo
        # para los periódicos, y nunca debe crear un aviso para uno de umbral.
        self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "threshold",
            "min_qty": 5.0,
        })
        self.env["mgs.stock.alert"]._mgs_cron_run_alerts()
        self.assertFalse(self.env["mgs.stock.alert.notice"].search([]))

    def test_marking_a_notice_read_does_not_affect_others(self):
        alert = self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "periodic",
            "interval_type": "weekly",
        })
        self.env["mgs.stock.alert"]._mgs_cron_run_alerts()
        alert.last_run = fields.Datetime.now() - timedelta(weeks=2)
        self.env["mgs.stock.alert"]._mgs_cron_run_alerts()
        notices = self.env["mgs.stock.alert.notice"].search([("alert_id", "=", alert.id)])
        self.assertEqual(len(notices), 2)
        notices[0].action_mark_read()
        self.assertTrue(notices[0].is_read)
        self.assertFalse(notices[1].is_read)


@tagged("post_install", "-at_install")
class TestStockAlertThreshold(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Tulipán de aviso", "is_storable": True,
        })

    def stock(self, quantity, cost=5.0):
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.product.id, "quantity": quantity, "unit_cost": cost,
        })]}).action_confirm()

    def test_is_triggered_when_stock_is_at_or_below_the_minimum(self):
        self.stock(4)
        alert = self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "threshold",
            "min_qty": 5.0,
        })
        self.assertTrue(alert.is_triggered)

    def test_is_not_triggered_once_stock_is_above_the_minimum(self):
        self.stock(20)
        alert = self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "threshold",
            "min_qty": 5.0,
        })
        self.assertFalse(alert.is_triggered)
