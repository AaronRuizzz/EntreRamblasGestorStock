# -*- coding: utf-8 -*-
"""Arranque de la compañía (models/res_company.py): nombre, moneda, país,
tipos de operación e idioma. Se ejecuta en cada `-u`, así que estos métodos
tienen que ser idempotentes — las pruebas los llaman una segunda vez sobre una
base que ya pasó por ellos al instalar el módulo."""
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.mi_gestor_stock.models.res_company import COMPANY_NAME, LANG_CODE


@tagged("post_install", "-at_install")
class TestCompanyBranding(TransactionCase):
    def test_apply_branding_sets_the_shop_name_currency_and_country(self):
        company = self.env.company
        company._mgs_apply_branding()
        self.assertEqual(company.name, COMPANY_NAME)
        self.assertEqual(company.currency_id, self.env.ref("base.EUR"))
        self.assertEqual(company.country_id, self.env.ref("base.es"))

    def test_apply_branding_is_idempotent_on_a_company_already_branded(self):
        company = self.env.company
        company._mgs_apply_branding()
        name, currency, country = company.name, company.currency_id, company.country_id
        # Segunda pasada (lo que hace un `-u` repetido): no debe cambiar nada.
        company._mgs_apply_branding()
        self.assertEqual(company.name, name)
        self.assertEqual(company.currency_id, currency)
        self.assertEqual(company.country_id, country)

    def test_apply_branding_renames_a_stale_my_company_partner(self):
        stale = self.env["res.partner"].create({"name": "My Company"})
        self.env.company._mgs_apply_branding()
        self.assertEqual(stale.name, COMPANY_NAME)

    def test_apply_branding_keeps_a_real_legal_name_and_offers_a_trade_name(self):
        company = self.env.company
        company.name = "Floristería Ejemplo SL"
        company._mgs_apply_branding()
        self.assertEqual(company.name, "Floristería Ejemplo SL")
        icp = self.env["ir.config_parameter"].sudo()
        self.assertTrue(icp.get_param("mgs.commercial_name"))
        # La pantalla de Configuración separa los dos nombres y cada uno va a su sitio.
        config = self.env["mgs.config"]._mgs_get()
        config.write({"mgs_commercial_name": "Entre Ramblas", "mgs_company_name": "Otra Razón SL"})
        self.assertEqual(company.name, "Otra Razón SL")
        self.assertEqual(icp.get_param("mgs.commercial_name"), "Entre Ramblas")

    def test_rename_picking_types_renames_pos_orders_and_the_default_warehouse(self):
        picking_type = self.env["stock.picking.type"].search([], limit=1)
        original_picking_name = picking_type.name
        picking_type.name = "PoS Orders"
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        original_warehouse_name = warehouse.name
        warehouse.name = "My Company"
        try:
            self.env.company._mgs_rename_picking_types()
            self.assertEqual(picking_type.name, "Pedidos TPV")
            self.assertEqual(warehouse.name, COMPANY_NAME)
        finally:
            picking_type.name = original_picking_name
            warehouse.name = original_warehouse_name

    def test_rename_picking_types_leaves_other_names_alone(self):
        picking_type = self.env["stock.picking.type"].search(
            [("name", "not in", ["PoS Orders", "PoS Orders Refund"])], limit=1)
        name = picking_type.name
        self.env.company._mgs_rename_picking_types()
        self.assertEqual(picking_type.name, name)


@tagged("post_install", "-at_install")
class TestCompanyPricelistDefaults(TransactionCase):
    def test_apply_pos_pricelist_defaults_turns_pricelists_on_for_every_pos(self):
        configs = self.env["pos.config"].search([])
        category = self.env["pos.category"].create({"name": "Solo demostración"})
        configs.write({
            "use_pricelist": False,
            "restrict_price_control": False,
            "limit_categories": True,
            "iface_available_categ_ids": [(6, 0, category.ids)],
        })
        self.env.company._mgs_apply_pos_pricelist_defaults()
        self.assertTrue(all(configs.mapped("use_pricelist")))
        self.assertTrue(all(configs.mapped("restrict_price_control")))
        self.assertFalse(any(configs.mapped("limit_categories")))
        self.assertFalse(configs.iface_available_categ_ids)

    def test_apply_pos_pricelist_defaults_does_nothing_without_a_pos_config(self):
        # No debe reventar en una instalación sin ninguna caja configurada todavía.
        self.env["pos.config"].search([]).unlink()
        self.env.company._mgs_apply_pos_pricelist_defaults()  # no debe lanzar


@tagged("post_install", "-at_install")
class TestCompanyShopPosConfig(TransactionCase):
    """La conversión de una caja restaurante no puede bloquear un ``-u``."""

    def _mark_shop_as_restaurant(self):
        shop = self.env.ref("mi_gestor_stock.pos_config_shop")
        # Este estado puede venir de una base anterior. Se escribe por SQL para
        # reproducirlo sin instalar el módulo opcional pos_restaurant durante
        # una prueba del addon.
        self.env.cr.execute(
            "UPDATE pos_config SET module_pos_restaurant = TRUE WHERE id = %s",
            [shop.id],
        )
        shop.invalidate_recordset(["module_pos_restaurant"])
        return shop

    def test_converts_a_restaurant_config_when_it_has_no_open_session(self):
        shop = self.env.ref("mi_gestor_stock.pos_config_shop")
        shop.name = "Restaurante"
        shop = self._mark_shop_as_restaurant()

        self.env.company._mgs_ensure_shop_pos_config()

        self.assertFalse(shop.module_pos_restaurant)
        self.assertEqual(shop.name, "Tienda")

    def test_preserves_a_custom_shop_name(self):
        shop = self.env.ref("mi_gestor_stock.pos_config_shop")
        shop.name = "Caja Centro"

        self.env.company._mgs_ensure_shop_pos_config()

        self.assertEqual(shop.name, "Caja Centro")

    def test_defers_conversion_when_the_restaurant_session_is_open(self):
        shop = self._mark_shop_as_restaurant()
        session = self.env["pos.session"].create({
            "config_id": shop.id,
            "user_id": self.env.user.id,
        })
        self.assertNotEqual(session.state, "closed")

        self.env.company._mgs_ensure_shop_pos_config()

        self.assertTrue(shop.module_pos_restaurant)
        self.assertEqual(self.env.ref("mi_gestor_stock.pos_config_shop"), shop)


@tagged("post_install", "-at_install")
class TestCompanySpanish(TransactionCase):
    def test_setup_spanish_leaves_spanish_active_and_english_inactive(self):
        self.env.company._mgs_setup_spanish()
        es = self.env["res.lang"].with_context(active_test=False).search(
            [("code", "=", LANG_CODE)], limit=1)
        en = self.env["res.lang"].with_context(active_test=False).search(
            [("code", "=", "en_US")], limit=1)
        self.assertTrue(es.active)
        self.assertFalse(en.active)

    def test_setup_spanish_sets_the_default_language_for_users_and_partners(self):
        self.env.company._mgs_setup_spanish()
        self.assertEqual(self.env["ir.default"]._get_model_defaults("res.partner").get("lang"), LANG_CODE)
        self.assertFalse(self.env["res.users"].with_context(active_test=False).search(
            [("lang", "!=", LANG_CODE)]))
        self.assertFalse(self.env["res.partner"].with_context(active_test=False).search(
            [("lang", "!=", LANG_CODE)]))

    def test_setup_spanish_renames_the_stock_administrator_name(self):
        admin = self.env.ref("base.user_admin")
        original = admin.name
        admin.name = "Mitchell Admin"
        try:
            self.env.company._mgs_setup_spanish()
            self.assertEqual(admin.name, "Administrador")
        finally:
            admin.name = original

    def test_setup_spanish_does_not_touch_an_administrator_already_renamed_by_hand(self):
        admin = self.env.ref("base.user_admin")
        original = admin.name
        admin.name = "Ana, la propietaria"
        try:
            self.env.company._mgs_setup_spanish()
            self.assertEqual(admin.name, "Ana, la propietaria")
        finally:
            admin.name = original


@tagged("post_install", "-at_install")
class TestCompanySpanishChart(TransactionCase):
    """Las dos guardas de _mgs_ensure_spanish_chart importan más que el propio
    `try_loading`: cargar un plan de verdad ya lo prueba Odoo, aquí solo hace
    falta comprobar CUÁNDO se llama y cuándo no. Por eso se parchea."""

    def test_does_nothing_if_the_company_already_has_a_spanish_chart(self):
        company = self.env.company
        self.assertTrue(company.chart_template and company.chart_template.startswith("es"))
        with patch.object(type(self.env["account.chart.template"]), "try_loading") as try_loading:
            company._mgs_ensure_spanish_chart()
        try_loading.assert_not_called()

    def test_does_nothing_if_there_is_already_real_accounting(self):
        company = self.env.company
        with patch.object(type(company), "chart_template", new="generic_coa"), \
             patch.object(type(company), "_existing_accounting", return_value=True), \
             patch.object(type(self.env["account.chart.template"]), "try_loading") as try_loading:
            company._mgs_ensure_spanish_chart()
        try_loading.assert_not_called()

    def test_loads_es_pymes_when_the_chart_is_not_spanish_and_nothing_is_booked(self):
        company = self.env.company
        with patch.object(type(company), "chart_template", new="generic_coa"), \
             patch.object(type(company), "_existing_accounting", return_value=False), \
             patch.object(type(self.env["account.chart.template"]), "try_loading") as try_loading:
            company._mgs_ensure_spanish_chart()
        try_loading.assert_called_once_with("es_pymes", company, install_demo=False)

    def test_a_failure_while_loading_is_swallowed_so_install_never_breaks(self):
        company = self.env.company
        with patch.object(type(company), "chart_template", new="generic_coa"), \
             patch.object(type(company), "_existing_accounting", return_value=False), \
             patch.object(type(self.env["account.chart.template"]), "try_loading",
                          side_effect=RuntimeError("boom")):
            company._mgs_ensure_spanish_chart()  # no debe propagar la excepción
