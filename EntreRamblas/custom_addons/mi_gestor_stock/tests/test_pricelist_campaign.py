from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged, new_test_user
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestPricelistCampaign(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa de tarifa", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "use_expiration_date": True,
            "taxes_id": [Command.clear()], "list_price": 2.0,
        })
        cls.now = fields.Datetime.now()

    def campaign(self, **vals):
        return self.env["mgs.pricelist.campaign"].create(dict({
            "name": "San Valentín de prueba",
            "date_start": self.now - timedelta(days=1),
            "date_end": self.now + timedelta(days=7),
            "compute_price": "discount", "percent_price": 10.0,
        }, **vals))

    # ------------------------------------------------------------------
    def test_discount_campaign_lowers_the_price_only_within_the_window(self):
        wiz = self.campaign()
        result = wiz.action_create()
        pricelist = self.env["product.pricelist"].browse(result["res_id"])
        self.assertEqual(pricelist.item_ids.compute_price, "percentage")
        self.assertEqual(pricelist.item_ids.percent_price, 10.0)
        self.assertEqual(pricelist.item_ids.applied_on, "3_global")

        inside = pricelist._get_product_price(self.rose, 1.0, date=self.now)
        self.assertAlmostEqual(inside, 1.8, places=2)  # 2.0 - 10%
        outside = pricelist._get_product_price(self.rose, 1.0, date=self.now + timedelta(days=30))
        self.assertEqual(outside, 2.0)  # fuera de fecha: precio normal

    def test_fixed_price_campaign_can_also_raise_the_price(self):
        wiz = self.campaign(compute_price="fixed", fixed_price=3.0)
        result = wiz.action_create()
        pricelist = self.env["product.pricelist"].browse(result["res_id"])
        price = pricelist._get_product_price(self.rose, 1.0, date=self.now)
        self.assertEqual(price, 3.0)

    def test_campaign_scoped_to_a_category_only_affects_that_category(self):
        categ = self.env["product.category"].create({"name": "Rosas de prueba"})
        self.rose.categ_id = categ
        other = self.env["product.product"].create({
            "name": "Otro producto de tarifa", "is_storable": True,
            "taxes_id": [Command.clear()], "list_price": 5.0,
        })
        wiz = self.campaign(categ_id=categ.id)
        result = wiz.action_create()
        pricelist = self.env["product.pricelist"].browse(result["res_id"])
        self.assertEqual(pricelist.item_ids.applied_on, "2_product_category")
        self.assertAlmostEqual(pricelist._get_product_price(self.rose, 1.0, date=self.now), 1.8, places=2)
        self.assertEqual(pricelist._get_product_price(other, 1.0, date=self.now), 5.0)  # otra categoría, sin tocar

    def test_creating_a_campaign_activates_pricelists_on_existing_pos_configs(self):
        self.pos_config.use_pricelist = False
        wiz = self.campaign()
        result = wiz.action_create()
        pricelist = self.env["product.pricelist"].browse(result["res_id"])
        self.pos_config.invalidate_recordset(["use_pricelist", "available_pricelist_ids"])
        self.assertTrue(self.pos_config.use_pricelist)
        self.assertIn(pricelist, self.pos_config.available_pricelist_ids)

    def test_margin_still_comes_from_real_cost_not_from_the_campaign_price(self):
        """El margen no se calcula del precio de venta, así que una tarifa que
        baja el precio no debe tocar el coste histórico de la línea."""
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.rose.id, "quantity": 10, "unit_cost": 1.2,
        })]}).action_confirm()
        wiz = self.campaign()
        result = wiz.action_create()
        pricelist = self.env["product.pricelist"].browse(result["res_id"])
        campaign_price = pricelist._get_product_price(self.rose, 1.0, date=self.now)

        session = self.env["pos.session"].create({"config_id": self.pos_config.id})
        session.set_opening_control(0, "")
        order = self.env["pos.order"].create({
            "session_id": session.id, "amount_tax": 0,
            "amount_total": campaign_price, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.rose.id, "qty": 1, "price_unit": campaign_price,
                "price_subtotal": campaign_price, "price_subtotal_incl": campaign_price,
            })],
        })
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)
        self.assertAlmostEqual(order.lines.total_cost, 1.2, places=2)
        self.assertNotEqual(order.lines.total_cost, campaign_price)

    def test_dates_and_amounts_are_validated(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.campaign(date_end=self.now - timedelta(days=10)).action_create()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.campaign(compute_price="discount", percent_price=0).action_create()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.campaign(compute_price="fixed", fixed_price=0).action_create()

    def test_only_the_owner_creates_campaigns(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login="pricelist_staff", groups="mi_gestor_stock.group_mgs_user")
        wiz = self.campaign()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            wiz.with_user(staff).action_create()
