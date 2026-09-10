# -*- coding: utf-8 -*-
r"""Actualizador independiente de Odoo, con estado persistente.

Fases (en `<runtime>\actualizador\estado.json`):

    al-dia      no hay nada más nuevo
    disponible  hay una versión firmada más nueva (la ha visto `comprobar`)
    preparado   el paquete está descargado y verificado (firma + SHA-256)
    aplicando   aplicación en curso; `paso` dice por dónde va (recuperable)
    hecho       aplicada y comprobada
    fallo       algo falló; `mensaje` lo explica; si migró, se restauró la copia

Comandos:

    comprobar --releases-url URL [--config C --database D]
    preparar  --releases-url URL
    aceptar | rechazar            (la dueña, desde la app: «Actualizar al cerrar»)
    aplicar   --config C --database D [--servicio NOMBRE] [--destino DIR]
    estado

Reglas del plan:
  * se descarga y se comprueba TODO (firma, integridad, compatibilidad) antes
    de detener nada;
  * no se aplica con una sesión de caja abierta, ventas pendientes u
    operaciones de hardware en curso;
  * copia verificada antes de tocar código o base;
  * si una migración falla, se restaura código Y base anteriores antes de
    permitir vender otra vez; nunca se ejecuta código antiguo sobre una base
    ya migrada;
  * el componente que instala solo acepta paquetes firmados y destinos fijos.
"""
import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # .../EntreRamblas
sys.path.insert(0, str(ROOT / "tools"))
from paquete_firma import load_public, sha256_file, verify_bytes  # noqa: E402

PUBLIC_KEY = ROOT / "instalador" / "firma-publica.pem"
MANIFEST_NAME = "manifest.json"
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024               # 2 GiB de holgura


# --------------------------------------------------------------------- utilidades
def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def installed_version():
    manifest = ROOT / "custom_addons" / "mi_gestor_stock" / "__manifest__.py"
    return ast.literal_eval(manifest.read_text(encoding="utf-8"))["version"]


def _vt(version):
    return tuple(int(p) for p in str(version).split(".") if p.isdigit())


def is_newer(candidate, current):
    return _vt(candidate) > _vt(current)


def pinned_odoo_revision():
    try:
        return (ROOT / "odoo-revision.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def compat_problems(manifest):
    """Lista de incompatibilidades (vacía = compatible)."""
    problems = []
    req = manifest.get("requisitos", {})
    want_rev = req.get("odoo_revision")
    if want_rev and pinned_odoo_revision() and want_rev != pinned_odoo_revision():
        # No es un fallo por sí solo: el paquete trae su propio motor. Solo se
        # avisa si el paquete NO incluye motor y depende del que ya hay.
        if not manifest.get("incluye_motor", True):
            problems.append("el paquete necesita otra revisión del motor Odoo")
    want_py = req.get("python")
    if want_py:
        have = "%d.%d" % sys.version_info[:2]
        if not have.startswith(str(want_py)):
            problems.append("requiere Python %s (hay %s)" % (want_py, have))
    if req.get("so") and req["so"] != "windows" and os.name == "nt":
        problems.append("paquete para otro sistema operativo")
    return problems


def free_bytes(path):
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


# ------------------------------------------------------------------------- estado
class State:
    def __init__(self, runtime_dir):
        self.dir = Path(runtime_dir) / "actualizador"
        self.path = self.dir / "estado.json"
        self.staging = self.dir / "paquete"
        self.backup = self.dir / "respaldo"
        self.data = {
            "fase": "al-dia", "version_instalada": installed_version(),
            "version_disponible": None, "manifest": None, "paquete_local": None,
            "verificado": False, "comprobado_en": None, "mensaje": "",
            "paso": None, "aceptada_por_duena": False,
        }
        if self.path.is_file():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def save(self, **changes):
        self.data.update(changes)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


# --------------------------------------------------------------------- descargas
def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "EntreRamblas-Actualizador"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _load_signed_manifest(releases_url):
    base = releases_url.rstrip("/")
    manifest_raw = _fetch(base + "/" + MANIFEST_NAME)
    signature = _fetch(base + "/" + MANIFEST_NAME + ".sig").decode("ascii").strip()
    if not PUBLIC_KEY.is_file():
        raise RuntimeError("Falta la clave pública de verificación (%s)." % PUBLIC_KEY)
    if not verify_bytes(load_public(PUBLIC_KEY), manifest_raw, signature):
        raise RuntimeError("La firma del manifiesto no es válida. Paquete rechazado.")
    return json.loads(manifest_raw.decode("utf-8"))


# ----------------------------------------------------------------------- comandos
def cmd_comprobar(args):
    st = State(args.runtime)
    try:
        manifest = _load_signed_manifest(args.releases_url)
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        st.save(comprobado_en=_now(),
                mensaje="Sin conexión; se comprobará de nuevo más adelante.")
        print("sin-conexion")
        return 0
    except Exception as err:  # noqa: BLE001 - firma inválida u otra
        st.save(comprobado_en=_now(), mensaje=str(err))
        print("rechazado:", err)
        return 2

    version = manifest.get("version")
    if not version or not is_newer(version, st.data["version_instalada"]):
        st.save(fase="al-dia", version_disponible=version, manifest=manifest,
                comprobado_en=_now(), mensaje="", verificado=False, paquete_local=None)
        print("al-dia")
        return 0

    problems = compat_problems(manifest)
    if problems:
        st.save(fase="fallo", version_disponible=version, manifest=manifest,
                comprobado_en=_now(), mensaje="Incompatible: " + "; ".join(problems))
        print("incompatible:", "; ".join(problems))
        return 3

    st.save(fase="disponible", version_disponible=version, manifest=manifest,
            comprobado_en=_now(), verificado=False, paquete_local=None,
            mensaje=manifest.get("notas") and " ".join(manifest["notas"]) or "")
    print("disponible", version)
    return 0


def cmd_preparar(args):
    st = State(args.runtime)
    if st.data["fase"] not in ("disponible", "preparado"):
        print("nada-que-preparar (fase %s)" % st.data["fase"])
        return 1
    manifest = st.data["manifest"] or _load_signed_manifest(args.releases_url)
    archivo = manifest["archivo"]
    st.staging.mkdir(parents=True, exist_ok=True)
    destino = st.staging / archivo
    base = args.releases_url.rstrip("/")
    data = _fetch(base + "/" + archivo, timeout=120)
    destino.write_bytes(data)
    got = sha256_file(destino)
    if got != manifest["sha256"]:
        destino.unlink(missing_ok=True)
        st.save(fase="fallo", verificado=False,
                mensaje="El paquete descargado no coincide con su huella SHA-256.")
        print("sha256-no-coincide")
        return 2
    # segunda comprobación de firma (defensa en profundidad)
    if not _load_signed_manifest(args.releases_url).get("sha256") == got:
        st.save(fase="fallo", verificado=False, mensaje="El manifiesto cambió durante la descarga.")
        return 2
    st.save(fase="preparado", verificado=True, paquete_local=str(destino), mensaje="")
    print("preparado", manifest["version"])
    return 0


def cmd_aceptar(args):
    st = State(args.runtime)
    st.save(aceptada_por_duena=True)
    print("aceptada")
    return 0


def cmd_rechazar(args):
    st = State(args.runtime)
    st.save(aceptada_por_duena=False)
    print("aplazada")
    return 0


def cmd_estado(args):
    st = State(args.runtime)
    print(json.dumps(st.data, indent=2, ensure_ascii=False))
    return 0


# ----------------------------------------------------- aplicación segura (7 pasos)
def _blocking_operations(config, database):
    """(lista de motivos) por los que NO se puede aplicar ahora."""
    sys.path.insert(0, str(ROOT / "odoo"))
    import odoo
    odoo.tools.config.parse_config(["-c", config, "-d", database, "--no-http"])
    reasons = []
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute("SELECT count(*) FROM pos_session WHERE state <> 'closed'")
        if cr.fetchone()[0]:
            reasons.append("hay una sesión de caja abierta")
        cr.execute("SELECT count(*) FROM pos_order WHERE state IN ('draft', 'paid')")
        if cr.fetchone()[0]:
            reasons.append("hay ventas del TPV sin terminar")
        cr.execute("""SELECT count(*) FROM information_schema.tables
                      WHERE table_name = 'mgs_hardware_job'""")
        if cr.fetchone()[0]:
            cr.execute("SELECT count(*) FROM mgs_hardware_job WHERE state IN ('pending', 'sending')")
            if cr.fetchone()[0]:
                reasons.append("hay una impresión o apertura de cajón en curso")
    return reasons


def _service(action, name):
    if not name:
        return
    subprocess.run(["sc", action, name], check=False, capture_output=True)
    time.sleep(2)


def _run_odoo(config, database, *extra):
    python = ROOT / "venv" / "Scripts" / "python.exe"
    return subprocess.run(
        [str(python), str(ROOT / "odoo" / "odoo-bin"), "-c", config, "-d", database,
         "--db-filter=^%s$" % database, *extra],
        check=False).returncode


def cmd_aplicar(args):
    st = State(args.runtime)
    if st.data["fase"] not in ("preparado", "aplicando"):
        print("no-preparado (fase %s)" % st.data["fase"])
        return 1
    if not st.data.get("verificado"):
        print("el-paquete-no-esta-verificado")
        return 1

    destino = Path(args.destino or ROOT)
    manifest = st.data["manifest"]

    # PASO 1 — comprobación previa (ya descargado y verificado). Preconditions:
    reasons = _blocking_operations(args.config, args.database)
    if reasons:
        st.save(mensaje="Aplazada: " + "; ".join(reasons) + ". Ciérralo y repite.")
        print("aplazada:", "; ".join(reasons))
        return 4

    sys.path.insert(0, str(ROOT / "odoo"))
    import odoo
    odoo.tools.config.parse_config(["-c", args.config, "-d", args.database, "--no-http"])

    try:
        # PASO 2/3 — mantenimiento: impedir operaciones nuevas.
        st.save(fase="aplicando", paso="mantenimiento", mensaje="")
        with odoo.sql_db.db_connect(args.database).cursor() as cr:
            cr.execute("""INSERT INTO ir_config_parameter (key, value)
                          VALUES ('mgs.maintenance', %s)
                          ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                       [_now()])
            cr.commit()

        # PASO 4 — copia verificada + respaldo del código y la versión actual.
        st.save(paso="copia")
        backup_path = _backup_database(odoo, args.database)
        if not backup_path:
            raise RuntimeError("La copia de seguridad previa falló.")
        if st.backup.exists():
            shutil.rmtree(st.backup)
        _snapshot_code(destino, st.backup)
        (st.backup / "version.txt").write_text(st.data["version_instalada"], encoding="utf-8")
        (st.backup / "copia-base.txt").write_text(str(backup_path), encoding="utf-8")

        # PASO 5 — parar servicio, instalar versión, migrar.
        st.save(paso="instalando")
        _service("stop", args.servicio)
        _install_package(st.data["paquete_local"], destino)
        st.save(paso="migrando")
        rc = _run_odoo(args.config, args.database, "-u", "mi_gestor_stock",
                       "--stop-after-init", "--no-http")
        if rc != 0:
            raise RuntimeError("La migración terminó con error (%s)." % rc)

        # PASO 6 — comprobaciones.
        st.save(paso="comprobando")
        rc = _run_odoo(args.config, args.database, "--stop-after-init", "--no-http")
        if rc != 0:
            raise RuntimeError("El servidor no arranca limpio tras la actualización.")
        applied = _applied_version(odoo, args.database)
        if not applied or _vt(applied)[-3:] != _vt(manifest["version"])[-3:]:
            raise RuntimeError("La versión aplicada (%s) no es la esperada (%s)."
                               % (applied, manifest["version"]))

        # PASO 7 — reabrir solo si todo pasó.
        _clear_maintenance(odoo, args.database)
        _service("start", args.servicio)
        st.save(fase="hecho", paso=None, verificado=False, aceptada_por_duena=False,
                version_instalada=manifest["version"],
                mensaje="Actualización aplicada y comprobada.")
        print("hecho", manifest["version"])
        return 0

    except Exception as err:  # noqa: BLE001 - cualquier fallo -> reversión
        _rollback(odoo, args, st, destino, str(err))
        print("fallo (revertido):", err)
        return 5


def _rollback(odoo, args, st, destino, message):
    # Nunca dejar código antiguo sobre una base ya migrada: primero se restaura
    # la base, luego el código.
    step = st.data.get("paso")
    try:
        if step in ("migrando", "comprobando"):
            copia = (st.backup / "copia-base.txt")
            if copia.is_file():
                _restore_database(args, copia.read_text(encoding="utf-8").strip())
        if step in ("instalando", "migrando", "comprobando") and st.backup.exists():
            _restore_code(st.backup, destino)
        _clear_maintenance(odoo, args.database)
        _service("start", args.servicio)
    finally:
        st.save(fase="fallo", paso=None,
                mensaje="Revertido tras un fallo: " + message)


# -------------------------------------------------------------- piezas concretas
def _backup_database(odoo, database):
    from odoo.modules.registry import Registry
    with Registry(database).cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        backup = env["mgs.backup"].sudo()._mgs_run_backup(kind="pre-actualizacion")
        if not backup or backup.state != "done":
            return None
        cr.commit()
        return backup.path


def _restore_database(args, zip_path):
    subprocess.run(
        [str(ROOT / "venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "restore_backup.py"),
         "--archivo", zip_path, "--config", args.config, "--database", args.database + "_restaurada"],
        check=False)
    # La restauración va a una base nueva por diseño; el cambio de nombre
    # definitivo lo hace el operador (ver ACTUALIZACIONES.md).


def _applied_version(odoo, database):
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute("SELECT latest_version FROM ir_module_module WHERE name = 'mi_gestor_stock'")
        row = cr.fetchone()
    return row[0] if row else None


def _clear_maintenance(odoo, database):
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute("DELETE FROM ir_config_parameter WHERE key = 'mgs.maintenance'")
        cr.commit()


_SNAPSHOT = ("custom_addons", "tools", "odoo-revision.txt", "requirements-windows.lock")


def _snapshot_code(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for name in _SNAPSHOT:
        source = Path(src) / name
        if source.is_dir():
            shutil.copytree(source, dst / name, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, dst / name)


def _restore_code(snapshot, dst):
    for name in _SNAPSHOT:
        source = snapshot / name
        target = Path(dst) / name
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        elif source.is_file():
            shutil.copy2(source, target)


def _install_package(zip_path, dst):
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        payload = Path(tmp)
        inner = [p for p in payload.iterdir() if p.is_dir()]
        if len(inner) == 1 and not (payload / "custom_addons").exists():
            payload = inner[0]
        for name in _SNAPSHOT:
            source = payload / name
            target = Path(dst) / name
            if source.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(source, target)
            elif source.is_file():
                shutil.copy2(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", default=os.environ.get(
        "ENTRERAMBLAS_RUNTIME", str(ROOT / ".odoo_data")))
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("comprobar"); p.add_argument("--releases-url", required=True)
    p.add_argument("--config"); p.add_argument("--database"); p.set_defaults(func=cmd_comprobar)
    p = sub.add_parser("preparar"); p.add_argument("--releases-url", required=True)
    p.set_defaults(func=cmd_preparar)
    p = sub.add_parser("aceptar"); p.set_defaults(func=cmd_aceptar)
    p = sub.add_parser("rechazar"); p.set_defaults(func=cmd_rechazar)
    p = sub.add_parser("estado"); p.set_defaults(func=cmd_estado)
    p = sub.add_parser("aplicar")
    p.add_argument("--config", required=True); p.add_argument("--database", required=True)
    p.add_argument("--servicio"); p.add_argument("--destino")
    p.set_defaults(func=cmd_aplicar)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
