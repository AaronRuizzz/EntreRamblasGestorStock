# -*- coding: utf-8 -*-
"""Acceso solo con contraseña: política, activación de un solo uso, clave de
recuperación que rota, límite persistente de intentos y una cuenta de
propietaria que gestiona la tienda pero no administra Odoo."""
from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..models.mgs_access import ThrottleError
from ..models.mgs_permissions import is_manager

GOOD_PW = "Rosa-Clavel-2026!"
OTHER_PW = "Azahar-Invierno-77"


@tagged("post_install", "-at_install")
class TestAccessModel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ctx = dict(cls.env.context, no_reset_password=True)
        cls.owner = new_test_user(
            cls.env(context=ctx), login="mgs_access_owner",
            groups="mi_gestor_stock.group_mgs_manager")
        cls.owner.mgs_is_owner = True
        cls.access = cls.env["mgs.access"]

    def test_password_policy_rejects_the_obvious(self):
        for bad in ["corta", "aaaaaaaaaaaaaa", "mgs_access_owner", "contraseña00"]:
            with self.assertRaises(ValidationError):
                self.access._check_password_policy(bad, "mgs_access_owner")
        self.access._check_password_policy(GOOD_PW, "mgs_access_owner")

    def test_activation_code_is_single_use(self):
        code = self.access._begin_activation(self.owner)
        self.assertFalse(self.owner.mgs_password_set)
        self.assertEqual(self.access._get().activation_state, "pending")
        with self.assertRaises(UserError):
            self.access._consume_activation("AAAA-BBBB-CCCC-DDDD", GOOD_PW, GOOD_PW)
        with self.assertRaises(ValidationError):
            self.access._consume_activation(code, GOOD_PW, "otra cosa")
        key = self.access._consume_activation(code, GOOD_PW, GOOD_PW)
        self.assertTrue(key)
        self.assertTrue(self.owner.mgs_password_set)
        self.assertEqual(self.access._get().activation_state, "used")
        with self.assertRaises(UserError):
            self.access._consume_activation(code, OTHER_PW, OTHER_PW)

    def test_recovery_key_rotates_and_invalidates_the_previous_one(self):
        code = self.access._begin_activation(self.owner)
        key1 = self.access._consume_activation(code, GOOD_PW, GOOD_PW)
        self.assertTrue(self.access._verify_recovery_key(key1))
        self.assertTrue(self.access._verify_recovery_key(" " + key1.lower() + " "))
        with self.assertRaises(UserError):
            self.access._recover_with_key("NOPE-NOPE-NOPE-NOPE", OTHER_PW, OTHER_PW)
        key2 = self.access._recover_with_key(key1, OTHER_PW, OTHER_PW)
        self.assertFalse(self.access._verify_recovery_key(key1))
        self.assertTrue(self.access._verify_recovery_key(key2))
        self.assertTrue(self.env["mgs.access.event"].search_count([("source", "=", "recuperar")]))

    def test_recovery_needs_a_key_that_meets_the_policy(self):
        code = self.access._begin_activation(self.owner)
        key1 = self.access._consume_activation(code, GOOD_PW, GOOD_PW)
        with self.assertRaises(ValidationError):
            self.access._recover_with_key(key1, "corta", "corta")

    def test_throttle_locks_after_repeated_failures_and_clears_on_success(self):
        throttle = self.env["mgs.auth.throttle"]
        for _ in range(throttle._MAX_FAILURES):
            throttle._register_failure("login")
        with self.assertRaises(ThrottleError):
            throttle._assert_open("login")
        throttle._register_success("login")
        throttle._assert_open("login")  # no salta

    def test_the_owner_runs_the_shop_but_is_not_an_odoo_admin(self):
        self.assertTrue(is_manager(self.env(user=self.owner)))
        self.assertFalse(self.owner.has_group("base.group_system"))
        self.assertFalse(self.owner.has_group("base.group_erp_manager"))

    def test_there_is_only_one_owner(self):
        other = new_test_user(
            self.env(context=dict(self.env.context, no_reset_password=True)),
            login="mgs_access_other", groups="mi_gestor_stock.group_mgs_manager")
        with self.assertRaises(ValidationError):
            other.mgs_is_owner = True

    def test_the_reset_trail_cannot_be_edited_or_deleted(self):
        event = self.env["mgs.access.event"].create(
            {"source": "configuracion", "note": "prueba"})
        with self.assertRaises(UserError):
            event.note = "cambiado"
        with self.assertRaises(UserError):
            event.unlink()

    def test_regenerate_wizard_requires_the_current_password(self):
        code = self.access._begin_activation(self.owner)
        self.access._consume_activation(code, GOOD_PW, GOOD_PW)
        wizard = self.env["mgs.access.regenerate"].with_user(self.owner).create(
            {"current_password": "no es"})
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.current_password = GOOD_PW
        wizard.action_confirm()
        self.assertTrue(wizard.done and wizard.new_key)


@tagged("post_install", "-at_install")
class TestDiagnostic(TransactionCase):
    def test_diagnostic_reports_the_expected_sections_without_secrets(self):
        import json
        data = self.env["mgs.diagnostic"]._gather()
        for key in ("modulo", "motor_odoo", "config_comun", "modulos_instalados"):
            self.assertIn(key, data)
            if isinstance(data[key], dict):
                self.assertNotIn("error", data[key])
        self.assertIn("mi_gestor_stock", {m["nombre"] for m in data["modulos_instalados"]})
        # Ni huellas de secretos ni contraseñas: el bloque de config, serializado.
        config_blob = json.dumps(data["config_comun"], ensure_ascii=False).lower()
        for secret in ("fingerprint", "password", "passwd", "contraseña", "vat", "nif"):
            self.assertNotIn(secret, config_blob)
        # El admin_passwd de odoo.conf no aparece por ningún lado.
        real_admin_passwd = self.env["ir.config_parameter"].sudo().get_param(
            "database.secret") or "x"
        self.assertNotIn(real_admin_passwd, self.env["mgs.diagnostic"]._gather_text())

    def test_diagnostic_download_returns_a_json_attachment(self):
        wizard = self.env["mgs.diagnostic"].create({"report_text": "{}"})
        action = wizard.action_download()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("/web/content/", action["url"])


@tagged("post_install", "-at_install")
class TestAccessHttp(HttpCase):
    def _make_owner(self, password_set):
        return self.env["res.users"].create({
            "name": "Dueña", "login": "mgs_http_owner",
            "password": GOOD_PW,
            "groups_id": [(6, 0, [self.env.ref("mi_gestor_stock.group_mgs_manager").id])],
            "mgs_is_owner": True, "mgs_password_set": password_set,
        })

    def test_configured_login_page_drops_the_user_field_and_offers_the_key(self):
        self._make_owner(password_set=True)
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("He olvidado mi contrase", response.text)
        self.assertNotIn('name="login"', response.text)
        self.assertNotIn("Reset Password", response.text)

    def test_pending_first_access_sends_you_to_the_wizard(self):
        owner = self._make_owner(password_set=True)
        self.env["mgs.access"]._begin_activation(owner)
        response = self.url_open("/web/login", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/mgs/primer-acceso", response.headers.get("Location", ""))

    def test_recovery_page_renders_without_email(self):
        self._make_owner(password_set=True)
        response = self.url_open("/mgs/recuperar")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Your Email", response.text)
        self.assertNotIn("Reset Password", response.text)
