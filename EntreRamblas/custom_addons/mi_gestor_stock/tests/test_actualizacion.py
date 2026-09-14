# -*- coding: utf-8 -*-
"""Firma Ed25519 de los paquetes, comparación de versiones y compatibilidad, y
la ventana de la app sobre el estado del actualizador."""
import importlib.util
import json
import sys
from pathlib import Path

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import config

_TOOLS = Path(__file__).resolve().parents[3] / "tools"


def _load(module_name):
    spec = importlib.util.spec_from_file_location(module_name, _TOOLS / (module_name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@tagged("post_install", "-at_install")
class TestPackageSignature(TransactionCase):
    def test_ed25519_sign_and_tamper_detection(self):
        firma = _load("paquete_firma")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        pub = key.public_key()
        payload = b'{"version": "18.0.4.0.0", "sha256": "abc"}'
        sig = firma.sign_bytes(key, payload)
        self.assertTrue(firma.verify_bytes(pub, payload, sig))
        self.assertFalse(firma.verify_bytes(pub, payload + b" ", sig))
        other = Ed25519PrivateKey.generate().public_key()
        self.assertFalse(firma.verify_bytes(other, payload, sig))

    def test_version_compare_and_compatibility(self):
        _load("paquete_firma")
        upd = _load("actualizador")
        self.assertTrue(upd.is_newer("18.0.4.0.0", "18.0.3.0.0"))
        self.assertFalse(upd.is_newer("18.0.3.0.0", "18.0.3.0.0"))
        self.assertFalse(upd.is_newer("18.0.2.9.9", "18.0.3.0.0"))
        # Un paquete que trae su propio motor no exige la revisión Odoo local.
        self.assertEqual(upd.compat_problems({"incluye_motor": True, "requisitos": {}}), [])
        problems = upd.compat_problems({"requisitos": {"python": "9.9"}})
        self.assertTrue(problems)


@tagged("post_install", "-at_install")
class TestEngineIntegrity(TransactionCase):
    def test_runtime_path_classification(self):
        mot = _load("verificar_motor")
        for path in (
            "odoo/http.py",
            "odoo/addons/base/models/ir_module.py",
            "addons/account/models/account_move.py",
            "addons/account/__manifest__.py",
            "addons/account/i18n/es.po",
            "addons/point_of_sale/static/src/app/pos_store.js",
        ):
            self.assertTrue(mot._is_runtime_path(path), path)
        for path in (
            "doc/index.rst",
            "LICENSE",
            "setup.py",
            "debian/control",
            "odoo/addons/base/tests/test_ir_model.py",
            "addons/account/tests/test_account_move.py",
            "addons/account/README.md",
        ):
            self.assertFalse(mot._is_runtime_path(path), path)

    def test_pinned_engine_has_no_local_modifications(self):
        mot = _load("verificar_motor")
        result = mot.check()
        if result["code"] == 4:
            self.skipTest("git no disponible en este entorno")
        # El commit fijado y, más allá del identificador, sin ficheros
        # versionados modificados ni añadidos. La ausencia de documentación o
        # ficheros de prueba no cuenta como manipulación.
        self.assertTrue(result["revision_coincide"], result)
        self.assertEqual(result["ficheros_modificados"], [], result)
        self.assertEqual(result["ficheros_ejecucion_ausentes"], [], result)
        self.assertEqual(result["ficheros_ejecucion_borrados"], [], result)
        self.assertTrue(result["ok"], result)

    def test_text_output_flags_a_tampered_engine(self):
        mot = _load("verificar_motor")
        texto = mot._texto({
            "code": 3, "estado": "modificado",
            "revision_actual": "abc", "revision_fijada": "abc",
            "ficheros_modificados": ["odoo/http.py"],
            "ficheros_ejecucion_ausentes": [], "ficheros_ejecucion_borrados": [],
        })
        self.assertIn("modificado", texto)
        self.assertIn("odoo/http.py", texto)


@tagged("post_install", "-at_install")
class TestUpdateWindow(TransactionCase):
    def _state_file(self, payload):
        path = Path(config.get("data_dir")) / "actualizador" / "estado.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_summary_reports_an_available_update(self):
        self._state_file({"fase": "disponible", "version_disponible": "18.0.9.0.0",
                          "version_instalada": "18.0.3.0.0", "aceptada_por_duena": False})
        summary = self.env["mgs.update"]._summary()
        self.assertTrue(summary["available"])
        self.assertIn("18.0.9.0.0", summary["label"])

    def test_summary_is_quiet_when_up_to_date(self):
        self._state_file({"fase": "al-dia"})
        self.assertFalse(self.env["mgs.update"]._summary()["available"])
        self.assertEqual(self.env["mgs.update"]._summary()["label"], "")

    def test_owner_accepts_update_at_close(self):
        path = self._state_file({
            "fase": "preparado", "version_disponible": "18.0.9.0.0",
            "aceptada_por_duena": False,
            "manifest": {"version": "18.0.9.0.0", "sha256": "0" * 64}})
        wizard = self.env["mgs.update"].action_open()
        rec = self.env["mgs.update"].browse(wizard["res_id"])
        rec.action_accept()
        self.assertTrue(json.loads(path.read_text(encoding="utf-8"))["aceptada_por_duena"])
        # Consentimiento vinculado a la versión y el hash exactos (hallazgo 9):
        # el servicio aplicador no se fía del booleano a secas.
        acceptance_path = path.parent / "aceptacion.json"
        self.assertTrue(acceptance_path.is_file())
        acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
        self.assertEqual(acceptance["version"], "18.0.9.0.0")
        self.assertEqual(acceptance["sha256"], "0" * 64)

    def test_accept_refuses_without_a_verified_manifest(self):
        self._state_file({"fase": "preparado", "version_disponible": "18.0.9.0.0",
                          "aceptada_por_duena": False})
        wizard = self.env["mgs.update"].action_open()
        rec = self.env["mgs.update"].browse(wizard["res_id"])
        with self.assertRaises(UserError):
            rec.action_accept()
