# -*- coding: utf-8 -*-
"""Actualizador (tools/actualizador.py): hallazgos 7, 8, 9, 10, 11, 24 de la
revisión 2026-09-10. Se cargan los módulos de tools/ con el mismo patrón que
test_actualizacion.py (_load), sin tocar mi_base_stock ni el servicio real:
todo corre contra archivos temporales y con subprocess.run parcheado."""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import odoo.sql_db
import odoo.tools
from odoo.tests import TransactionCase, tagged

_TOOLS = Path(__file__).resolve().parents[3] / "tools"


def _load(module_name):
    spec = importlib.util.spec_from_file_location(module_name, _TOOLS / (module_name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@tagged("post_install", "-at_install")
class TestServiceGate(TransactionCase):
    def test_aplicar_refuses_outside_the_privileged_service(self):
        # Hallazgo 9: invocar `aplicar` a mano (sin privilegios) no debe
        # tocar nada. Solo tools/update_service.py pone esta variable.
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            os.environ.pop("ENTRERAMBLAS_UPDATE_SERVICE", None)
            args = argparse.Namespace(runtime=raw, config="no-existe", database="mgs_x",
                                      servicio=None, destino=None)
            rc = upd.cmd_aplicar(args)
        self.assertEqual(rc, 6)


@tagged("post_install", "-at_install")
class TestVersionUnit(TransactionCase):
    def test_engine_is_only_installed_when_the_manifest_declares_it(self):
        # Hallazgo 10: _SNAPSHOT ignoraba odoo/, venv/(ahora python/+wheels/),
        # instalador/ y los lanzadores aunque incluye_motor=true.
        upd = _load("actualizador")
        with_engine = upd._version_unit({"incluye_motor": True})
        without_engine = upd._version_unit({"incluye_motor": False})
        for name in ("odoo", "python", "wheels", "instalador"):
            self.assertIn(name, with_engine)
            self.assertNotIn(name, without_engine)
        for name in ("custom_addons", "tools", "odoo-revision.txt"):
            self.assertIn(name, with_engine)
            self.assertIn(name, without_engine)

    def test_install_package_installs_engine_and_launcher_when_declared(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = root / "payload"
            for rel in ("custom_addons/marker.txt", "tools/marker.txt",
                       "odoo/marker.txt", "instalador/marker.txt",
                       "python/marker.txt", "wheels/marker.txt"):
                path = payload / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("NUEVO", encoding="utf-8")
            zip_path = root / "paquete.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for path in payload.rglob("*"):
                    if path.is_file():
                        zf.write(path, path.relative_to(payload))

            dst = root / "dst"
            (dst / "odoo").mkdir(parents=True)
            (dst / "odoo" / "marker.txt").write_text("ANTIGUO", encoding="utf-8")

            upd._install_package(str(zip_path), dst, {"incluye_motor": True})
            self.assertEqual((dst / "odoo" / "marker.txt").read_text(encoding="utf-8"), "NUEVO")
            self.assertTrue((dst / "instalador" / "marker.txt").is_file())
            self.assertTrue((dst / "python" / "marker.txt").is_file())
            self.assertTrue((dst / "custom_addons" / "marker.txt").is_file())

    def test_install_package_rejects_a_manifest_that_lies_about_the_engine(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = root / "payload"
            (payload / "custom_addons").mkdir(parents=True)
            (payload / "custom_addons" / "marker.txt").write_text("x", encoding="utf-8")
            zip_path = root / "paquete.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for path in payload.rglob("*"):
                    if path.is_file():
                        zf.write(path, path.relative_to(payload))
            with self.assertRaises(RuntimeError):
                upd._install_package(str(zip_path), root / "dst", {"incluye_motor": True})


@tagged("post_install", "-at_install")
class TestRollbackCommand(TransactionCase):
    def test_restore_database_uses_a_positional_archivo_and_check_true(self):
        # Hallazgo 7: actualizador.py llamaba a restore_backup.py con
        # --archivo, que ni existe ahí (es posicional), y con check=False: el
        # rollback de base fallaba en silencio.
        upd = _load("actualizador")
        args = argparse.Namespace(config="config.local", database="mgs_prueba")
        with patch.object(upd.subprocess, "run") as run, \
             patch.object(upd, "_run_odoo", return_value=0), \
             patch.object(upd, "_swap_databases", return_value="mgs_prueba_migrada_x") as swap:
            run.return_value = subprocess.CompletedProcess([], 0)
            upd._restore_database(args, "backup.zip")
        call = run.call_args
        cmd = call.args[0]
        self.assertIn("backup.zip", cmd)
        # posicional: justo detrás de restore_backup.py, sin --archivo antes.
        idx = cmd.index("backup.zip")
        self.assertNotEqual(cmd[idx - 1], "--archivo")
        self.assertTrue(call.kwargs.get("check"))
        self.assertTrue(swap.called)

    def test_restore_database_does_not_activate_a_database_that_fails_to_start(self):
        upd = _load("actualizador")
        args = argparse.Namespace(config="config.local", database="mgs_prueba")
        with patch.object(upd.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(upd, "_run_odoo", return_value=1), \
             patch.object(upd, "_swap_databases") as swap:
            with self.assertRaises(RuntimeError):
                upd._restore_database(args, "backup.zip")
        self.assertFalse(swap.called)


@tagged("post_install", "-at_install")
class TestResumeSafety(TransactionCase):
    def test_resuming_after_migrando_preserves_the_original_backup(self):
        # Hallazgo 8: cmd_aplicar aceptaba el estado "aplicando" pero volvía a
        # empezar desde el principio sin respetar `paso`, borrando el
        # respaldo original. Aquí se reproduce ese punto de reanudación.
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            runtime = Path(raw) / "runtime"
            st = upd.State(str(runtime))
            st.backup.mkdir(parents=True)
            marker = st.backup / "MARCADOR_RESPALDO_ORIGINAL"
            marker.write_text("no-debe-desaparecer", encoding="utf-8")
            (st.backup / "COMPLETO").write_text("2026-01-01T00:00:00Z", encoding="utf-8")
            st.save(fase="aplicando", paso="migrando", verificado=True,
                    aceptada_por_duena=True,
                    manifest={"version": "18.0.99.0.0", "incluye_motor": False},
                    paquete_local=str(Path(raw) / "no-se-usa.zip"))

            config_path = Path(raw) / "falso.conf"
            config_path.write_text("[options]\n", encoding="utf-8")
            args = argparse.Namespace(runtime=str(runtime), config=str(config_path),
                                      database="mgs_prueba", servicio=None, destino=raw)
            os.environ["ENTRERAMBLAS_UPDATE_SERVICE"] = "1"
            manifest = {"version": "18.0.99.0.0", "incluye_motor": False}
            try:
                with patch.object(upd, "_reverify_staged_package", return_value=manifest), \
                     patch.object(upd, "_check_free_space", return_value=None), \
                     patch.object(upd, "_drain_blocking_operations", return_value=[]), \
                     patch.object(upd, "_install_package"), \
                     patch.object(upd, "_run_odoo", return_value=0), \
                     patch.object(upd, "_applied_version", return_value="18.0.99.0.0"), \
                     patch.object(upd, "_clear_maintenance"), \
                     patch.object(upd, "_service"), \
                     patch.object(odoo.sql_db, "db_connect"), \
                     patch.object(odoo.tools.config, "parse_config"):
                    rc = upd.cmd_aplicar(args)
            finally:
                os.environ.pop("ENTRERAMBLAS_UPDATE_SERVICE", None)

            self.assertEqual(rc, 0)
            self.assertTrue(marker.exists(), "el respaldo original no debería tocarse al reanudar")

    def test_resuming_with_paso_advanced_but_no_complete_backup_refuses(self):
        # paso ya avanzado a "migrando" pero SIN el marcador COMPLETO ni
        # directorio de respaldo: estado inconsistente. No hay nada que
        # revertir (nunca se tocó código ni base), así que la reversión en sí
        # no falla (return 5, "revertido"); lo importante es que NO continúa
        # instalando/migrando a ciegas sin red de seguridad.
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            runtime = Path(raw) / "runtime"
            st = upd.State(str(runtime))
            st.save(fase="aplicando", paso="migrando", verificado=True,
                    manifest={"version": "18.0.99.0.0", "incluye_motor": False},
                    paquete_local="no-se-usa.zip")
            config_path = Path(raw) / "falso.conf"
            config_path.write_text("[options]\n", encoding="utf-8")
            args = argparse.Namespace(runtime=str(runtime), config=str(config_path),
                                      database="mgs_prueba", servicio=None, destino=raw)
            os.environ["ENTRERAMBLAS_UPDATE_SERVICE"] = "1"
            manifest = {"version": "18.0.99.0.0", "incluye_motor": False}
            try:
                with patch.object(upd, "_reverify_staged_package", return_value=manifest), \
                     patch.object(upd, "_check_free_space", return_value=None), \
                     patch.object(upd, "_drain_blocking_operations", return_value=[]), \
                     patch.object(upd, "_install_package") as install, \
                     patch.object(upd, "_run_odoo") as run_odoo, \
                     patch.object(upd, "_service"), \
                     patch.object(odoo.sql_db, "db_connect"), \
                     patch.object(odoo.tools.config, "parse_config"):
                    rc = upd.cmd_aplicar(args)
            finally:
                os.environ.pop("ENTRERAMBLAS_UPDATE_SERVICE", None)
            self.assertEqual(rc, 5)
            self.assertEqual(upd.State(str(runtime)).data["fase"], "fallo")
            self.assertFalse(install.called, "no debería instalar sin respaldo completo")
            self.assertFalse(run_odoo.called, "no debería migrar sin respaldo completo")


@tagged("post_install", "-at_install")
class TestReverifyStagedPackage(TransactionCase):
    """Hallazgo 9: el componente con privilegios no debe fiarse de
    estado.json (lo escribe el proceso menos privilegiado de la app)."""

    def _stage(self, st, upd, package_bytes, manifest_dict, key=None,
              tamper_signature=False, write_acceptance=True):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        firma = _load("paquete_firma")
        key = key or Ed25519PrivateKey.generate()
        st.staging.mkdir(parents=True, exist_ok=True)
        package_path = st.staging / "paquete.zip"
        package_path.write_bytes(package_bytes)
        manifest_dict = dict(manifest_dict, sha256=upd.sha256_file(package_path))
        raw = json.dumps(manifest_dict, ensure_ascii=False).encode("utf-8")
        signature = firma.sign_bytes(key, raw)
        (st.staging / upd.MANIFEST_NAME).write_bytes(raw)
        sig_text = ("tampered" if tamper_signature else signature)
        (st.staging / (upd.MANIFEST_NAME + ".sig")).write_text(sig_text + "\n", encoding="ascii")
        st.save(paquete_local=str(package_path))
        if write_acceptance:
            (st.dir / "aceptacion.json").write_text(json.dumps({
                "version": manifest_dict["version"], "sha256": manifest_dict["sha256"],
            }), encoding="utf-8")
        return key, manifest_dict

    def _public_pem(self, key):
        from cryptography.hazmat.primitives import serialization
        return key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def test_accepts_a_correctly_signed_and_accepted_package(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            key, manifest = self._stage(
                st, upd, b"contenido-del-paquete",
                {"version": "18.0.99.0.0", "incluye_motor": False})
            upd.PUBLIC_KEY = Path(raw) / "publica.pem"
            upd.PUBLIC_KEY.write_bytes(self._public_pem(key))
            result = upd._reverify_staged_package(st)
            self.assertEqual(result["version"], "18.0.99.0.0")

    def test_rejects_a_hash_that_does_not_match_the_signed_manifest(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            key, manifest = self._stage(
                st, upd, b"contenido-original",
                {"version": "18.0.99.0.0", "incluye_motor": False})
            upd.PUBLIC_KEY = Path(raw) / "publica.pem"
            upd.PUBLIC_KEY.write_bytes(self._public_pem(key))
            # El paquete en disco se sustituye DESPUÉS de firmar: como si algo
            # (o alguien, sin la clave privada) lo hubiera alterado.
            (st.staging / "paquete.zip").write_bytes(b"contenido-manipulado")
            with self.assertRaises(RuntimeError):
                upd._reverify_staged_package(st)

    def test_rejects_a_bad_signature(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            key, manifest = self._stage(
                st, upd, b"contenido", {"version": "18.0.99.0.0", "incluye_motor": False},
                tamper_signature=True)
            upd.PUBLIC_KEY = Path(raw) / "publica.pem"
            upd.PUBLIC_KEY.write_bytes(self._public_pem(key))
            with self.assertRaises(Exception):
                upd._reverify_staged_package(st)

    def test_rejects_acceptance_bound_to_a_different_version(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            key, manifest = self._stage(
                st, upd, b"contenido", {"version": "18.0.99.0.0", "incluye_motor": False},
                write_acceptance=False)
            (st.dir / "aceptacion.json").write_text(json.dumps({
                "version": "18.0.1.0.0", "sha256": manifest["sha256"]}), encoding="utf-8")
            upd.PUBLIC_KEY = Path(raw) / "publica.pem"
            upd.PUBLIC_KEY.write_bytes(self._public_pem(key))
            with self.assertRaises(RuntimeError):
                upd._reverify_staged_package(st)

    def test_rejects_missing_acceptance(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            key, manifest = self._stage(
                st, upd, b"contenido", {"version": "18.0.99.0.0", "incluye_motor": False},
                write_acceptance=False)
            upd.PUBLIC_KEY = Path(raw) / "publica.pem"
            upd.PUBLIC_KEY.write_bytes(self._public_pem(key))
            with self.assertRaises(RuntimeError):
                upd._reverify_staged_package(st)


@tagged("post_install", "-at_install")
class TestServiceControl(TransactionCase):
    def test_service_raises_when_the_wanted_state_never_arrives(self):
        # Hallazgo 11: antes era `sc <accion>` + sleep(2) fijo, sin comprobar
        # nada de verdad.
        upd = _load("actualizador")
        with patch.object(upd.subprocess, "run") as run, patch.object(upd.time, "sleep"):
            run.return_value = subprocess.CompletedProcess(
                [], 0, stdout="SERVICE_NAME: x\n        STATE              : 4  RUNNING\n")
            with self.assertRaises(RuntimeError):
                upd._service("stop", "AUDIT_ONLY_NO_REAL_SERVICE", timeout=3)

    def test_service_returns_when_the_wanted_state_is_confirmed(self):
        upd = _load("actualizador")
        with patch.object(upd.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess(
                [], 0, stdout="SERVICE_NAME: x\n        STATE              : 1  STOPPED\n")
            upd._service("stop", "AUDIT_ONLY_NO_REAL_SERVICE", timeout=5)  # no lanza


@tagged("post_install", "-at_install")
class TestFreeSpaceGuard(TransactionCase):
    def test_check_free_space_blocks_when_the_destination_is_tight(self):
        # Hallazgo 24: MIN_FREE_BYTES y free_bytes estaban definidos y no se
        # usaban en ningún sitio.
        upd = _load("actualizador")

        class _FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a, **k):
                pass

            def fetchone(self):
                return (0,)

        class _FakeConn:
            def cursor(self):
                return _FakeCursor()

        class _FakeOdoo:
            class sql_db:
                @staticmethod
                def db_connect(name):
                    return _FakeConn()

            class tools:
                class config:
                    @staticmethod
                    def filestore(name):
                        return "/no/existe"

        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            with patch.object(upd, "free_bytes", return_value=1024):  # 1 KiB libres
                problem = upd._check_free_space(
                    Path(raw), st, {"tamano_instalado": 10 * 1024 ** 3}, _FakeOdoo, "mgs_x")
        self.assertIsNotNone(problem)
        self.assertIn("MiB", problem)

    def test_preparar_refuses_to_download_without_space(self):
        upd = _load("actualizador")
        with tempfile.TemporaryDirectory() as raw:
            st = upd.State(str(Path(raw) / "runtime"))
            st.save(fase="disponible",
                    manifest={"version": "18.0.99.0.0", "archivo": "x.zip",
                             "sha256": "0" * 64, "tamano": 50 * 1024 ** 3})
            args = argparse.Namespace(runtime=str(Path(raw) / "runtime"), releases_url="http://x")
            with patch.object(upd, "free_bytes", return_value=1024):
                rc = upd.cmd_preparar(args)
        self.assertEqual(rc, 7)
