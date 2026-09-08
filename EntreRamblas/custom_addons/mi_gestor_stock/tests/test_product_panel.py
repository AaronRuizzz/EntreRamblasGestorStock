# -*- coding: utf-8 -*-
"""Los tres endpoints que alimentan las pantallas OWL (product_template.py):
mgs_find_by_barcode (escáner), mgs_home_summary (inicio) y mgs_dashboard_data
(panel de Stock). Se rompen en silencio si nadie los prueba: el frontend solo
ve un panel vacío, no un traceback."""
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged("post_install", "-at_install")
class TestFindByBarcode(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Rosa con código", "is_storable": True,
            "barcode": "8412345678905", "default_code": "REF-ROSA",
        })

    def test_matches_the_scanned_barcode(self):
        result = self.env["product.template"].mgs_find_by_barcode("8412345678905")
        self.assertEqual(result["id"], self.product.product_tmpl_id.id)

    def test_falls_back_to_the_internal_reference(self):
        result = self.env["product.template"].mgs_find_by_barcode("REF-ROSA")
        self.assertEqual(result["id"], self.product.product_tmpl_id.id)

    def test_returns_false_when_nothing_matches(self):
        self.assertFalse(self.env["product.template"].mgs_find_by_barcode("0000000000000"))

    def test_returns_false_for_an_empty_scan(self):
        self.assertFalse(self.env["product.template"].mgs_find_by_barcode("   "))

    def test_strips_the_configured_prefix_before_matching(self):
        config = self.env["mgs.config"]._mgs_get()
        config.scan_strip_prefix = "SUP-"
        result = self.env["product.template"].mgs_find_by_barcode("SUP-8412345678905")
        self.assertEqual(result["id"], self.product.product_tmpl_id.id)

    def test_a_user_without_the_shop_group_cannot_scan(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
                               login="mgs_panel_outsider")
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["product.template"].with_user(staff).mgs_find_by_barcode("8412345678905")


@tagged("post_install", "-at_install")
class TestHomeSummary(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Gerbera de inicio", "is_storable": True,
        })

    def test_counts_storable_products(self):
        before = self.env["product.template"].mgs_home_summary()["products"]
        self.env["product.product"].create({"name": "Otra gerbera", "is_storable": True})
        after = self.env["product.template"].mgs_home_summary()["products"]
        self.assertEqual(after, before + 1)

    def test_a_manager_sees_is_manager_true(self):
        self.assertTrue(self.env["product.template"].mgs_home_summary()["is_manager"])

    def test_a_shop_user_without_manager_group_sees_is_manager_false(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
                               login="mgs_panel_staff", groups="mi_gestor_stock.group_mgs_user")
        summary = self.env["product.template"].with_user(staff).mgs_home_summary()
        self.assertFalse(summary["is_manager"])
        self.assertFalse(summary["backup_warning"])

    def test_alerts_add_up_threshold_and_unread_periodic_notices(self):
        before = self.env["product.template"].mgs_home_summary()["alerts"]
        self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "threshold",
            "min_qty": 1000.0,  # sin stock: siempre por debajo, aviso garantizado
        })
        self.env["mgs.stock.alert.notice"].create({
            "product_id": self.product.product_tmpl_id.id, "name": "Aviso de prueba",
        })
        after = self.env["product.template"].mgs_home_summary()["alerts"]
        self.assertEqual(after, before + 2)

    def test_a_user_without_the_shop_group_cannot_open_the_home_summary(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
                               login="mgs_panel_stranger")
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["product.template"].with_user(staff).mgs_home_summary()


@tagged("post_install", "-at_install")
class TestDashboardData(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Peonía de panel", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True,
        })

    def stock(self, quantity, days=30, cost=5.0):
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.product.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]}).action_confirm()

    def test_a_triggered_threshold_alert_shows_up_with_no_notice_id(self):
        self.stock(3, days=30)
        self.env["mgs.stock.alert"].create({
            "product_id": self.product.product_tmpl_id.id, "alert_type": "threshold",
            "min_qty": 5.0,
        })
        data = self.env["product.template"].mgs_dashboard_data()
        threshold_alerts = [a for a in data["alerts"] if a["kind"] == "threshold"]
        self.assertEqual(len(threshold_alerts), 1)
        self.assertEqual(threshold_alerts[0]["product_id"], self.product.product_tmpl_id.id)
        self.assertFalse(threshold_alerts[0]["notice_id"])

    def test_an_unread_periodic_notice_shows_up_with_its_id(self):
        notice = self.env["mgs.stock.alert.notice"].create({
            "product_id": self.product.product_tmpl_id.id, "name": "Resumen semanal",
        })
        data = self.env["product.template"].mgs_dashboard_data()
        periodic_alerts = [a for a in data["alerts"] if a["kind"] == "periodic"]
        self.assertEqual([a["notice_id"] for a in periodic_alerts], [notice.id])

    def test_a_read_notice_does_not_show_up(self):
        notice = self.env["mgs.stock.alert.notice"].create({
            "product_id": self.product.product_tmpl_id.id, "name": "Resumen leído",
        })
        notice.action_mark_read()
        data = self.env["product.template"].mgs_dashboard_data()
        self.assertFalse([a for a in data["alerts"] if a["kind"] == "periodic"])

    def test_a_lot_expiring_within_three_days_is_listed_as_expiring(self):
        self.stock(5, days=2)
        data = self.env["product.template"].mgs_dashboard_data()
        self.assertTrue(any(e["product_id"] == self.product.product_tmpl_id.id
                            for e in data["expiring"]))

    def test_a_lot_far_from_expiring_is_not_listed(self):
        self.stock(5, days=30)
        data = self.env["product.template"].mgs_dashboard_data()
        self.assertFalse(any(e["product_id"] == self.product.product_tmpl_id.id
                             for e in data["expiring"]))

    def test_low_stock_is_ordered_by_quantity_ascending(self):
        self.stock(1, days=30)
        data = self.env["product.template"].mgs_dashboard_data()
        quantities = [row["qty"] for row in data["low_stock"]]
        self.assertEqual(quantities, sorted(quantities))

    def test_products_are_grouped_under_their_category(self):
        self.stock(5, days=30)
        data = self.env["product.template"].mgs_dashboard_data()
        categ_id = self.product.categ_id.id
        group = next(c for c in data["categories"] if c["id"] == categ_id)
        self.assertIn(self.product.product_tmpl_id.id, [p["id"] for p in group["products"]])

    def test_currency_is_the_company_currency_symbol(self):
        data = self.env["product.template"].mgs_dashboard_data()
        self.assertEqual(data["currency"], self.env.company.currency_id.symbol)
