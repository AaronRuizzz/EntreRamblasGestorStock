# -*- coding: utf-8 -*-
"""Instalación limpia y runtime propio (revisión 2026-09-10, hallazgos 2, 3, 4,
12, 17). Prueba lo que la suite no cubría: el árbol de arranque, la verificación
sin Git y la provisión de la propietaria sobre cualquier base."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from odoo.tests import TransactionCase, tagged

_TOOLS = Path(__file__).resolve().parents[3] / "tools"
_RUNTIME_ROOT = _TOOLS.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _TOOLS / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@tagged("post_install", "-at_install")
class TestConfigureRuntimeAllowExisting(TransactionCase):
    def test_populated_directory_needs_the_flag(self):
        script = _TOOLS / "configure_runtime.py"
        with tempfile.TemporaryDirectory() as raw:
            work = Path(raw) / "runtime"
            (work / "instalacion").mkdir(parents=True)
            (work / "pgdata").mkdir()
            fake_pg = Path(raw) / "pgbin"
            fake_pg.mkdir()
            for exe in ("psql.exe", "pg_dump.exe"):
                (fake_pg / exe).touch()
            env = dict(os.environ, MGS_DB_PASSWORD="solo-para-la-prueba")
            base = [sys.executable, str(script), "--directory", str(work),
                    "--pg-bin", str(fake_pg)]

            blocked = subprocess.run(base, capture_output=True, text=True, env=env)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("nueva o vac", blocked.stderr)

            ok = subprocess.run(base + ["--allow-existing"], capture_output=True,
                                text=True, env=env)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue((work / "odoo.local").is_file())

            again = subprocess.run(base + ["--allow-existing"], capture_output=True,
                                   text=True, env=env)
            self.assertNotEqual(again.returncode, 0)


@tagged("post_install", "-at_install")
class TestEngineIntegrityWithoutGit(TransactionCase):
    def test_hash_mode_detects_a_tampered_file(self):
        mot = _load("verificar_motor")
        firma = _load("paquete_firma")
        generar = _load("generar_integridad")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "tools").mkdir()
            (root / "custom_addons").mkdir()
            (root / "instalador").mkdir()
            (root / "odoo" / "odoo").mkdir(parents=True)
            (root / "odoo-revision.txt").write_text("f" * 40, encoding="utf-8")
            (root / "tools" / "algo.py").write_text("value = 1\n", encoding="utf-8")
            (root / "odoo" / "odoo" / "http.py").write_text("x = 1\n", encoding="utf-8")

            data = generar.build(root)
            (root / "integridad.json").write_text(
                json.dumps(data, sort_keys=True, indent=1), encoding="utf-8")

            key = Ed25519PrivateKey.generate()
            pub = root / "instalador" / "firma-publica.pem"
            pub.write_bytes(key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo))
            sig = firma.sign_bytes(key, (root / "integridad.json").read_bytes())
            (root / "integridad.json.sig").write_text(sig + "\n", encoding="ascii")

            for attr, value in (("ROOT", root), ("ENGINE", root / "odoo"),
                                ("PIN_FILE", root / "odoo-revision.txt"),
                                ("DIST_MANIFEST", root / "integridad.json"),
                                ("DIST_SIG", root / "integridad.json.sig"),
                                ("PUBLIC_KEY", pub)):
                setattr(mot, attr, value)

            self.assertEqual(mot.check()["code"], 0, mot.check())

            (root / "tools" / "algo.py").write_text("value = 999\n", encoding="utf-8")
            tampered = mot.check()
            self.assertEqual(tampered["code"], 3, tampered)
            self.assertIn("tools/algo.py", tampered["ficheros_modificados"])

    def test_hash_mode_rejects_a_bad_signature(self):
        mot = _load("verificar_motor")
        real_pub = (_RUNTIME_ROOT / "instalador" / "firma-publica.pem").read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "instalador").mkdir()
            (root / "integridad.json").write_text('{"ficheros": {}}', encoding="utf-8")
            (root / "integridad.json.sig").write_text("bm90LWEtc2ln\n", encoding="ascii")
            (root / "instalador" / "firma-publica.pem").write_bytes(real_pub)
            for attr, value in (("ROOT", root), ("ENGINE", root / "odoo"),
                                ("DIST_MANIFEST", root / "integridad.json"),
                                ("DIST_SIG", root / "integridad.json.sig"),
                                ("PUBLIC_KEY", root / "instalador" / "firma-publica.pem")):
                setattr(mot, attr, value)
            result = mot.check()
            self.assertEqual(result["code"], 3)
            self.assertFalse(result["firma_valida"])


@tagged("post_install", "-at_install")
class TestEnvironmentCheck(TransactionCase):
    def test_flags_a_python_base_outside_the_app(self):
        env_mod = _load("verificar_entorno")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "venv").mkdir()
            (root / "venv" / "pyvenv.cfg").write_text(
                "home = C:\\Users\\otro\\AppData\\Local\\Programs\\Python\\Python312\n"
                "version = 3.12.0\n", encoding="utf-8")
            (root / "requirements-windows.lock").write_text("pip==23.2.1\n", encoding="utf-8")
            env_mod.ROOT = root
            env_mod.LOCK = root / "requirements-windows.lock"
            env_mod.PYVENV = root / "venv" / "pyvenv.cfg"
            result = env_mod.check()
            self.assertIn(result["code"], (2, 3))
            self.assertFalse(result["ok"])
            self.assertTrue(any("pyvenv.cfg" in d or "fuera de la" in d
                                for d in result["detalles"]))


@tagged("post_install", "-at_install")
class TestOwnerProvisioning(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Access = self.env["mgs.access"]
        Users = self.env["res.users"].sudo()
        Users.search([("mgs_is_owner", "=", True)]).write({"mgs_is_owner": False})
        # mgs_validation es una base persistente entre ejecuciones: un -u
        # anterior ya pudo haber COMMITEADO (fuera de esta transacción de
        # prueba) una cuenta "propietaria" real vía la migración 18.0.4.0.0;
        # además, setUpClass de OTRAS clases de esta misma tanda de pruebas
        # no está protegido por el savepoint por-test y puede dejar estado a
        # medias visible aquí. Se aparta con un login garantizado único y se
        # fuerza el flush para no depender del orden en que el ORM aplace
        # esta escritura frente a la de la propia prueba (admin.login =
        # "propietaria"), que si no puede chocar en el mismo flush.
        admin = self.env.ref("base.user_admin")
        stray = Users.search([("login", "=", "propietaria")]) - admin
        if stray:
            stray.login = "propietaria-anterior-%s" % uuid.uuid4().hex[:12]
            self.env.flush_all()

    def test_provision_is_idempotent_and_assigns_a_sender(self):
        code = self.Access._mgs_provision_owner()
        self.assertTrue(code)
        again = self.Access._mgs_provision_owner()
        self.assertIsNone(again)
        owners = self.env["res.users"].search([("mgs_is_owner", "=", True)])
        self.assertEqual(len(owners), 1)
        self.assertNotEqual(owners.login, "admin")
        self.assertTrue(owners.has_group("mi_gestor_stock.group_mgs_manager"))
        self.assertTrue(owners.partner_id.email)

    def test_recovers_admin_login_when_it_was_renamed_to_propietaria(self):
        admin = self.env.ref("base.user_admin")
        admin.login = "propietaria"
        self.env.flush_all()
        self.Access._mgs_provision_owner()
        self.assertEqual(admin.login, "admin")
        owner = self.env["res.users"]._mgs_owner()
        self.assertTrue(owner)
        self.assertNotEqual(owner.id, admin.id)

    def test_company_sender_is_local_and_non_routable(self):
        self.Access._mgs_ensure_company_sender()
        icp = self.env["ir.config_parameter"].sudo()
        self.assertTrue((icp.get_param("mail.catchall.domain") or "").endswith(".invalid"))

    def test_company_email_is_the_real_shop_email_without_touching_custom_ones(self):
        company = self.env.company
        for placeholder in (False, "tienda@entreramblas.invalid", "TIENDA@entreramblas.invalid"):
            company.email = placeholder
            self.Access._mgs_ensure_company_sender()
            self.assertEqual(company.email, "entreramblasclavelyazahar@gmail.com")
            self.assertEqual(company.partner_id.email, "entreramblasclavelyazahar@gmail.com")
        company.email = "otra@tienda.example"
        self.Access._mgs_ensure_company_sender()
        self.assertEqual(company.email, "otra@tienda.example")
        # El remitente técnico interno se conserva, sin verse.
        icp = self.env["ir.config_parameter"].sudo()
        self.assertTrue((icp.get_param("mail.catchall.domain") or "").endswith(".invalid"))


@tagged("post_install", "-at_install")
class TestCompareDiagnostics(TransactionCase):
    """Hallazgo 22: se ignoraban la fecha general y el nombre de base, pero se
    comparaba historico_versiones[].aplicada entero: una base nueva y una
    migrada con la MISMA versión salían "distintas" solo por las fechas de
    instalación."""

    def _write(self, tmp, name, data):
        path = Path(tmp) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_same_version_different_install_history_counts_as_equal(self):
        cmp_mod = _load("comparar_diagnosticos")
        with tempfile.TemporaryDirectory() as tmp:
            a = self._write(tmp, "a.json", {
                "generado": "2026-01-01T00:00:00", "base_datos": "equipo_a",
                "modulo": {"aplicado": "18.0.4.0.0", "estado": "installed",
                          "historico_versiones": [
                              {"version": "18.0.4.0.0", "aplicada": "2026-01-01T00:00:00"}]},
            })
            b = self._write(tmp, "b.json", {
                "generado": "2026-02-15T10:00:00", "base_datos": "equipo_b",
                "modulo": {"aplicado": "18.0.4.0.0", "estado": "installed",
                          "historico_versiones": [
                              {"version": "18.0.3.0.0", "aplicada": "2026-01-01T00:00:00"},
                              {"version": "18.0.4.0.0", "aplicada": "2026-02-15T10:00:00"}]},
            })
            import sys
            old_argv = sys.argv
            try:
                sys.argv = ["comparar_diagnosticos.py", a, b]
                rc = cmp_mod.main()
            finally:
                sys.argv = old_argv
        self.assertEqual(rc, 0)

    def test_different_applied_version_counts_as_a_difference(self):
        cmp_mod = _load("comparar_diagnosticos")
        with tempfile.TemporaryDirectory() as tmp:
            a = self._write(tmp, "a.json", {
                "generado": "x", "base_datos": "equipo_a",
                "modulo": {"aplicado": "18.0.4.0.0", "historico_versiones": []}})
            b = self._write(tmp, "b.json", {
                "generado": "y", "base_datos": "equipo_b",
                "modulo": {"aplicado": "18.0.3.0.0", "historico_versiones": []}})
            import sys
            old_argv = sys.argv
            try:
                sys.argv = ["comparar_diagnosticos.py", a, b]
                rc = cmp_mod.main()
            finally:
                sys.argv = old_argv
        self.assertEqual(rc, 1)
