# -*- coding: utf-8 -*-
"""Que la app quede como un gestor de floristería y no un ERP: los nueve
menús raíz nativos ocultos («Ajustes» incluido), la app propia cerrada a
quien no tiene ningún grupo de la tienda, y las pantallas que sustituyen a
formularios/listas nativos apuntando de verdad a sus vistas propias."""
from lxml import etree

from odoo.tests import TransactionCase, tagged, new_test_user

# Grupos de tienda: raíz + las seis entradas que Fase 2 dejó con
# groups="group_mgs_user" (antes, sin groups, visibles a cualquier interno).
USER_MENUS = ["mi_gestor_stock." + m for m in (
    "menu_mgs_root", "menu_mgs_sell", "menu_mgs_stock", "menu_mgs_stock_panel",
    "menu_mgs_stock_products", "menu_mgs_stock_alerts", "menu_mgs_scrap",
)]
# Todo lo que en mgs_menus.xml lleva groups="group_mgs_manager" en el propio
# <menuitem> (no solo heredado de un padre): la propietaria las ve, la
# dependienta no.
MANAGER_MENUS = ["mi_gestor_stock." + m for m in (
    "menu_mgs_events", "menu_mgs_reception", "menu_mgs_catalog_import",
    "menu_mgs_reports", "menu_mgs_reports_sales", "menu_mgs_reports_top",
    "menu_mgs_reports_consumption", "menu_mgs_reports_monthly",
    "menu_mgs_reports_sessions", "menu_mgs_settings",
    "menu_mgs_settings_devices", "menu_mgs_settings_backups", "menu_mgs_hardware_jobs",
    "menu_mgs_settings_security", "menu_mgs_settings_access_events",
    "menu_mgs_settings_diagnostic",
)]
NATIVE_ROOT_MENUS = [
    "mail.menu_root_discuss", "contacts.menu_contacts",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
    "point_of_sale.menu_point_root", "account.menu_finance",
    "stock.menu_stock_root", "base.menu_management", "base.menu_tests",
    "base.menu_administration",
]


@tagged("post_install", "-at_install")
class TestNativeMenusHidden(TransactionCase):
    def test_the_nine_native_root_menus_are_inactive(self):
        for xmlid in NATIVE_ROOT_MENUS:
            menu = self.env.ref(xmlid)
            self.assertFalse(menu.active, "%s debería estar inactivo" % xmlid)


@tagged("post_install", "-at_install")
class TestAppMenuVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dependienta = new_test_user(
            cls.env, login="mgs_menu_dependienta", groups="mi_gestor_stock.group_mgs_user")
        cls.propietaria = new_test_user(
            cls.env, login="mgs_menu_propietaria", groups="mi_gestor_stock.group_mgs_manager")
        cls.outsider = new_test_user(cls.env, login="mgs_menu_outsider")  # sin ningún grupo de tienda

    def visible(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_a_user_without_any_shop_group_sees_none_of_the_app(self):
        visible = self.visible(self.outsider)
        for xmlid in USER_MENUS:
            self.assertNotIn(self.env.ref(xmlid).id, visible, "%s no debería verse" % xmlid)

    def test_shop_staff_sees_exactly_the_daily_menus(self):
        visible = self.visible(self.dependienta)
        for xmlid in USER_MENUS:
            self.assertIn(self.env.ref(xmlid).id, visible, "%s debería verse" % xmlid)
        for xmlid in MANAGER_MENUS:
            self.assertNotIn(self.env.ref(xmlid).id, visible,
                             "%s es solo de la propietaria" % xmlid)

    def test_the_owner_sees_the_staff_menus_and_her_own(self):
        visible = self.visible(self.propietaria)
        for xmlid in USER_MENUS + MANAGER_MENUS:
            self.assertIn(self.env.ref(xmlid).id, visible, "%s debería verse" % xmlid)


@tagged("post_install", "-at_install")
class TestActionsUseOwnViews(TransactionCase):
    """Las acciones que antes caían en una vista nativa (Fase 3) ahora
    apuntan a una propia: comprobado por xmlid, no solo "existe una vista"."""

    def view_ids_of(self, action_xmlid):
        action = self.env.ref("mi_gestor_stock." + action_xmlid)
        return set(action.view_ids.mapped("view_id.id")) | ({action.view_id.id} if action.view_id else set())

    def test_the_product_form_hides_the_erp_smart_buttons_pages_and_chatter(self):
        # product.template no fija un view_id propio en la acción: se
        # combina por herencia sobre la vista nativa
        # (product.product_template_only_form_view). Lo que hay que
        # comprobar es el resultado combinado, no la acción.
        # sudo(): get_view recorta del arch los elementos con `groups` que
        # el usuario que pregunta no tiene (la pestaña "Contabilidad" pide
        # account.group_account_readonly) — aquí interesa el arch completo.
        combined = self.env["product.template"].sudo().get_view(view_type="form")
        arch = etree.fromstring(combined["arch"])
        button_box = arch.xpath("//div[@name='button_box']")
        self.assertTrue(button_box)
        self.assertEqual(button_box[0].get("invisible"), "1")
        # "Contabilidad" (account) no se comprueba aquí: cuelga de otra vista
        # base (product_template_form_view) que esta pantalla no usa.
        pages = arch.xpath("//page[@name='pos']")
        self.assertTrue(pages, "falta la pestaña pos")
        self.assertEqual(pages[0].get("invisible"), "1")
        self.assertFalse(arch.xpath("//chatter"), "el chatter debería haberse quitado")

    def test_sales_reports_use_their_own_list_and_search(self):
        for action_xmlid in ("action_mgs_report_sales", "action_mgs_report_top_products"):
            action = self.env.ref("mi_gestor_stock." + action_xmlid)
            self.assertEqual(action.search_view_id,
                             self.env.ref("mi_gestor_stock.view_mgs_sales_search"))
            self.assertIn(self.env.ref("mi_gestor_stock.view_mgs_sales_list").id,
                          self.view_ids_of(action_xmlid))
            self.assertNotIn(self.env.ref("point_of_sale.report_pos_order_view_tree").id,
                             self.view_ids_of(action_xmlid))


@tagged("post_install", "-at_install")
class TestEventQuotePrintButton(TransactionCase):
    def test_the_event_form_has_a_header_button_to_print_the_quote(self):
        # event_form llevó js_class="mgs_clean_form" (quita el engranaje de
        # acciones), así que sin este botón el presupuesto dejaría de
        # imprimirse desde ningún sitio: report_mgs_event está solo
        # enlazado a mgs.event por binding_model_id, no por menú propio.
        # El botón se declara como name="%(action_report_mgs_event)d": ese
        # xmlid ya llega resuelto al id numérico en el arch guardado, así
        # que se compara contra ese id, no contra el texto del xmlid.
        report_action = self.env.ref("mi_gestor_stock.action_report_mgs_event")
        arch = self.env.ref("mi_gestor_stock.event_form").arch_db
        buttons = etree.fromstring(arch).xpath(
            "//header/button[@type='action' and @name='%s']" % report_action.id)
        self.assertEqual(len(buttons), 1, "falta el botón de imprimir en la cabecera")
        self.assertTrue(report_action.binding_model_id)
