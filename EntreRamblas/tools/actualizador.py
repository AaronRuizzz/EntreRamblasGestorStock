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


def _verify_manifest_bytes(manifest_raw, signature):
    if not PUBLIC_KEY.is_file():
        raise RuntimeError("Falta la clave pública de verificación (%s)." % PUBLIC_KEY)
    if not verify_bytes(load_public(PUBLIC_KEY), manifest_raw, signature):
        raise RuntimeError("La firma del manifiesto no es válida. Paquete rechazado.")
    return json.loads(manifest_raw.decode("utf-8"))


def _fetch_signed_manifest_raw(releases_url):
    """Descarga manifest.json + su firma y devuelve (manifiesto, bytes crudos,
    firma). Los bytes crudos y la firma son lo que permite RE-verificar más
    tarde sin red, contra la clave pública (instalador/firma-publica.pem, de
    solo lectura para el proceso de la app): el diccionario ya reserializado
    con json.dumps no reproduciría los mismos bytes firmados."""
    base = releases_url.rstrip("/")
    manifest_raw = _fetch(base + "/" + MANIFEST_NAME)
    signature = _fetch(base + "/" + MANIFEST_NAME + ".sig").decode("ascii").strip()
    manifest = _verify_manifest_bytes(manifest_raw, signature)
    return manifest, manifest_raw, signature


def _load_signed_manifest(releases_url):
    return _fetch_signed_manifest_raw(releases_url)[0]


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

    # Espacio ANTES de descargar: el zip, más margen para extraerlo después
    # (~2x su tamaño) y el margen fijo de holgura.
    needed = (manifest.get("tamano") or 0) * 3 + MIN_FREE_BYTES
    have = free_bytes(st.staging)
    if have is not None and needed and have < needed:
        st.save(fase="fallo", verificado=False,
                mensaje="Sin espacio para descargar la actualización (%d MiB libres, "
                       "se necesitan ~%d MiB)." % (have // (1 << 20), needed // (1 << 20)))
        print("sin-espacio")
        return 7

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
    # Segunda comprobación de firma (defensa en profundidad: el manifiesto
    # pudo cambiar durante la descarga) que ADEMÁS deja los bytes crudos
    # verificados en el staging, para que el servicio aplicador pueda
    # revalidar la firma él mismo sin fiarse de estado.json (hallazgo 9).
    fresh, manifest_raw, signature = _fetch_signed_manifest_raw(args.releases_url)
    if fresh.get("sha256") != got:
        st.save(fase="fallo", verificado=False, mensaje="El manifiesto cambió durante la descarga.")
        return 2
    (st.staging / MANIFEST_NAME).write_bytes(manifest_raw)
    (st.staging / (MANIFEST_NAME + ".sig")).write_text(signature + "\n", encoding="ascii")
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


# ----------------------------------------------------- aplicación segura (pasos)
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


def _drain_blocking_operations(config, database, timeout=60, interval=3):
    """Con el mantenimiento ya puesto (no entran operaciones nuevas), espera
    un poco a que las que estuvieran en curso terminen solas antes de aplazar
    de verdad. Devuelve la lista de motivos que sigan bloqueando al agotar el
    plazo (vacía si se pudo drenar)."""
    deadline = time.monotonic() + timeout
    reasons = _blocking_operations(config, database)
    while reasons and time.monotonic() < deadline:
        time.sleep(interval)
        reasons = _blocking_operations(config, database)
    return reasons


def _parse_sc_state(output):
    for line in output.splitlines():
        line = line.strip()
        if line.upper().startswith("STATE"):
            # p.ej. "STATE              : 4  RUNNING"
            parts = line.split(":", 1)[1].strip().split()
            if len(parts) >= 2:
                return parts[1].upper()
    return None


def _service(action, name, timeout=120):
    """Controla el servicio Windows y ESPERA a que el cambio de estado se
    confirme de verdad. Antes: `sc <action>` + `sleep(2)` fijo, que no
    comprobaba nada — `_install_package` podía sobrescribir código con Odoo
    todavía vivo (hallazgo 11). El supervisor admite hasta 100s para una
    parada ordenada (`windows_service.py`); aquí se da margen extra y se
    lanza si no se confirma."""
    if not name:
        return
    subprocess.run(["sc", action, name], check=False, capture_output=True)
    wanted = "STOPPED" if action == "stop" else "RUNNING"
    deadline = time.monotonic() + timeout
    state = None
    while time.monotonic() < deadline:
        query = subprocess.run(["sc", "query", name], check=False,
                               capture_output=True, text=True)
        state = _parse_sc_state(query.stdout)
        if state == wanted:
            return
        time.sleep(1)
    raise RuntimeError("El servicio %s no llegó a %s en %ds (último estado: %s)."
                       % (name, wanted, timeout, state))


def _run_odoo(config, database, *extra):
    # Se ejecuta con el MISMO intérprete que corre este proceso: cuando lo
    # invoca el servicio aplicador (tools/update_service.py), eso es el
    # CPython vendorizado, no el venv de la app — necesario para poder
    # reemplazar el venv sin que el propio proceso se bloquee a sí mismo.
    return subprocess.run(
        [sys.executable, str(ROOT / "odoo" / "odoo-bin"), "-c", config, "-d", database,
         "--db-filter=^%s$" % database, *extra],
        check=False).returncode


# ----------------------------------------------------------------- espacio (H24)
def _dir_size(path):
    total = 0
    try:
        for entry in Path(path).rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _min_apply_space(manifest, odoo, database):
    """Estimación conservadora del espacio necesario para aplicar, por
    volumen: el árbol instalado nuevo (además del respaldo del código actual,
    que ocupa aproximadamente lo mismo) en `destino`; el dump de la base más
    la copia del filestore en el volumen de datos."""
    installed_size = manifest.get("tamano_instalado") or manifest.get("tamano") or 0
    try:
        with odoo.sql_db.db_connect(database).cursor() as cr:
            cr.execute("SELECT pg_database_size(%s)", [database])
            db_size = cr.fetchone()[0] or 0
    except Exception:  # noqa: BLE001 - estimación, no bloquear por esto
        db_size = 0
    filestore_size = 0
    try:
        filestore_size = _dir_size(odoo.tools.config.filestore(database))
    except Exception:  # noqa: BLE001
        pass
    return {
        "destino": installed_size * 2 + MIN_FREE_BYTES,
        "datos": db_size + filestore_size + MIN_FREE_BYTES,
    }


def _check_free_space(destino, st, manifest, odoo, database):
    needs = _min_apply_space(manifest, odoo, database)
    problems = []
    have_dest = free_bytes(destino)
    if have_dest is not None and have_dest < needs["destino"]:
        problems.append("destino (%s): %d MiB libres, se necesitan ~%d MiB"
                        % (destino, have_dest // (1 << 20), needs["destino"] // (1 << 20)))
    have_data = free_bytes(st.dir)
    if have_data is not None and have_data < needs["datos"]:
        problems.append("datos (%s): %d MiB libres, se necesitan ~%d MiB"
                        % (st.dir, have_data // (1 << 20), needs["datos"] // (1 << 20)))
    return "; ".join(problems) if problems else None


def _reverify_staged_package(st):
    """El componente con privilegios no se fía de `estado.json`: lo escribe
    el proceso de la app (LocalService), menos privilegiado, que podría estar
    comprometido o simplemente tener un error. Re-verifica desde cero:

      * la firma Ed25519 de los bytes CRUDOS del manifiesto guardados en el
        staging (`cmd_preparar` los deja ahí), contra la clave pública — un
        fichero de solo lectura para ese proceso menos privilegiado;
      * el SHA-256 del paquete ya descargado, contra ese manifiesto
        RE-verificado (no contra la copia de estado.json);
      * la compatibilidad (versión, revisión de Odoo si no incluye motor);
      * que exista un consentimiento (`aceptacion.json`) vinculado EXACTAMENTE
        a esa versión y ese SHA-256 — no basta con `aceptada_por_duena` a
        secas, que es un booleano en el mismo estado.json editable.

    Devuelve el manifiesto re-verificado o lanza si algo no cuadra."""
    manifest_path = st.staging / MANIFEST_NAME
    sig_path = st.staging / (MANIFEST_NAME + ".sig")
    if not manifest_path.is_file() or not sig_path.is_file():
        raise RuntimeError("Falta el manifiesto firmado en el staging; no se aplica sin él.")
    manifest = _verify_manifest_bytes(manifest_path.read_bytes(),
                                      sig_path.read_text(encoding="ascii").strip())

    package_path = st.data.get("paquete_local")
    if not package_path or not Path(package_path).is_file():
        raise RuntimeError("Falta el paquete descargado; no se aplica.")
    if sha256_file(package_path) != manifest.get("sha256"):
        raise RuntimeError("El paquete en disco no coincide con el SHA-256 firmado.")

    problems = compat_problems(manifest)
    if problems:
        raise RuntimeError("Paquete incompatible: " + "; ".join(problems))

    try:
        acceptance = json.loads((st.dir / "aceptacion.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RuntimeError(
            "No hay consentimiento registrado de la propietaria para esta versión.")
    if (acceptance.get("version") != manifest.get("version")
            or acceptance.get("sha256") != manifest.get("sha256")):
        raise RuntimeError(
            "El consentimiento registrado no corresponde a esta versión/paquete "
            "(pudo haberse aceptado una versión distinta). No se aplica.")
    return manifest


def cmd_aplicar(args):
    # Componente con privilegios únicamente: este comando escribe en el
    # destino de instalación y para/arranca el servicio. El servicio
    # aplicador (tools/update_service.py) es el único llamador autorizado;
    # invocarlo a mano no toca nada (hallazgo 9).
    if os.environ.get("ENTRERAMBLAS_UPDATE_SERVICE") != "1":
        print("no-autorizado: aplicar solo se ejecuta desde el servicio "
             "EntreRamblasActualizador")
        return 6

    st = State(args.runtime)
    if st.data["fase"] not in ("preparado", "aplicando"):
        print("no-preparado (fase %s)" % st.data["fase"])
        return 1

    destino = Path(args.destino) if args.destino else ROOT
    try:
        manifest = _reverify_staged_package(st)
    except Exception as err:  # noqa: BLE001 - cualquier fallo de verificación -> no aplicar
        st.save(fase="fallo", paso=None, mensaje="Verificación propia del servicio: %s" % err)
        print("verificacion-fallida:", err)
        return 1
    # Reanudación: si ya estábamos "aplicando", `paso` dice por dónde.
    resuming_step = st.data.get("paso") if st.data["fase"] == "aplicando" else None

    sys.path.insert(0, str(ROOT / "odoo"))
    import odoo
    odoo.tools.config.parse_config(["-c", args.config, "-d", args.database, "--no-http"])

    # PASO 0 — espacio libre ANTES de tocar nada (hallazgo 24).
    problem = _check_free_space(destino, st, manifest, odoo, args.database)
    if problem:
        st.save(fase="fallo", paso=None, mensaje="Sin espacio suficiente: " + problem)
        print("sin-espacio:", problem)
        return 7

    try:
        # PASO 1/2 — mantenimiento (cierra la entrada de operaciones nuevas;
        # lo consulta mgs.permissions._assert_not_maintenance) y solo LUEGO
        # se comprueba que no queden operaciones en curso que drenar. Antes
        # se comprobaba una vez al principio y ya está: entre la comprobación
        # y parar el servicio podía colarse una venta.
        if resuming_step in (None, "mantenimiento"):
            st.save(fase="aplicando", paso="mantenimiento", mensaje="")
            with odoo.sql_db.db_connect(args.database).cursor() as cr:
                cr.execute("""INSERT INTO ir_config_parameter (key, value)
                              VALUES ('mgs.maintenance', %s)
                              ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                           [_now()])
                cr.commit()

        reasons = _drain_blocking_operations(args.config, args.database)
        if reasons:
            _clear_maintenance(odoo, args.database)
            st.save(fase="preparado", paso=None,
                    mensaje="Aplazada: " + "; ".join(reasons) + ". Ciérralo y repite.")
            print("aplazada:", "; ".join(reasons))
            return 4

        # PASO 3 — copia verificada del estado DEFINITIVO (con mantenimiento
        # ya puesto: nada nuevo puede colarse desde aquí) + respaldo del
        # código y la versión actuales. El respaldo, una vez COMPLETO, es
        # INMUTABLE para el resto de esta función: reanudar después de este
        # punto nunca lo vuelve a tocar (hallazgo 8).
        backup_marker = st.backup / "COMPLETO"
        if not backup_marker.is_file():
            if resuming_step not in (None, "mantenimiento", "copia"):
                raise RuntimeError(
                    "Estado inconsistente: paso=%s sin respaldo completo en %s. "
                    "No se continúa sin red de seguridad." % (resuming_step, st.backup))
            st.save(paso="copia")
            backup_path = _backup_database(odoo, args.database)
            if not backup_path:
                raise RuntimeError("La copia de seguridad previa falló.")
            if st.backup.exists():
                shutil.rmtree(st.backup)
            _snapshot_code(destino, st.backup)
            (st.backup / "version.txt").write_text(st.data["version_instalada"], encoding="utf-8")
            (st.backup / "copia-base.txt").write_text(str(backup_path), encoding="utf-8")
            backup_marker.write_text(_now(), encoding="utf-8")

        # PASO 4 — parar servicio (verificado), instalar versión, migrar.
        # Reanudar desde aquí es seguro: instalar sobrescribe por completo
        # cada componente desde el paquete ya verificado, y `-u` es idempotente.
        st.save(paso="instalando")
        _service("stop", args.servicio)
        _install_package(st.data["paquete_local"], destino, manifest)
        st.save(paso="migrando")
        rc = _run_odoo(args.config, args.database, "-u", "mi_gestor_stock",
                       "--stop-after-init", "--no-http")
        if rc != 0:
            raise RuntimeError("La migración terminó con error (%s)." % rc)

        # PASO 5 — comprobaciones.
        st.save(paso="comprobando")
        rc = _run_odoo(args.config, args.database, "--stop-after-init", "--no-http")
        if rc != 0:
            raise RuntimeError("El servidor no arranca limpio tras la actualización.")
        applied = _applied_version(odoo, args.database)
        if not applied or _vt(applied)[-3:] != _vt(manifest["version"])[-3:]:
            raise RuntimeError("La versión aplicada (%s) no es la esperada (%s)."
                               % (applied, manifest["version"]))

        # PASO 6 — reabrir SOLO si todo pasó, y comprobar que arranca de
        # verdad: no se marca "hecho" si el servicio no llega a RUNNING.
        _clear_maintenance(odoo, args.database)
        _service("start", args.servicio)
        st.save(fase="hecho", paso=None, verificado=False, aceptada_por_duena=False,
                version_instalada=manifest["version"],
                mensaje="Actualización aplicada y comprobada.")
        print("hecho", manifest["version"])
        return 0

    except Exception as err:  # noqa: BLE001 - cualquier fallo -> reversión
        try:
            _rollback(odoo, args, st, destino, str(err))
        except Exception as rollback_err:  # noqa: BLE001 - la reversión misma falló
            print("fallo critico: la reversion tambien fallo:", rollback_err)
            return 6
        print("fallo (revertido):", err)
        return 5


def _rollback(odoo, args, st, destino, message):
    """Nunca deja código NUEVO sobre una base restaurada, ni código ANTIGUO
    sirviendo una base a medio migrar: primero se restaura el código, y solo
    ENTONCES se restaura la base — `_restore_database` verifica que arranca
    limpio con ese código ya en su sitio antes de activarla (ver hallazgo 7).

    Si la propia reversión falla, el servicio queda DETENIDO y el estado en
    `fallo`: no se finge una recuperación que no ha ocurrido, y quien llama
    (`cmd_aplicar`) no vuelve a arrancar nada."""
    step = st.data.get("paso")
    try:
        if step in ("instalando", "migrando", "comprobando") and st.backup.exists():
            _restore_code(st.backup, destino)
        if step in ("migrando", "comprobando"):
            copia = (st.backup / "copia-base.txt")
            if copia.is_file():
                _restore_database(args, copia.read_text(encoding="utf-8").strip())
    except Exception as rollback_err:
        st.save(fase="fallo", paso=None,
                mensaje="LA REVERSIÓN FALLÓ (servicio detenido; revisar antes de "
                       "reintentar): %s. Motivo original: %s" % (rollback_err, message))
        raise
    _clear_maintenance(odoo, args.database)
    _service("start", args.servicio)
    st.save(fase="fallo", paso=None, mensaje="Revertido tras un fallo: " + message)


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
    """Restaura la copia en una base de cuarentena, comprueba que arranca
    limpio con el código anterior YA restaurado, y solo entonces la pone en
    el lugar de la base activa mediante un renombrado atómico. Nunca se deja
    código antiguo sirviendo la base migrada: si algo de esto falla, la
    excepción sube y `_rollback` deja el servicio parado con `fase="fallo"`,
    en vez de fingir una reversión que no ocurrió."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    rollback_db = "%s_rollback_%s" % (args.database, stamp)
    python = ROOT / "venv" / "Scripts" / "python.exe"
    # `archivo` es POSICIONAL en restore_backup.py; check=True para que un
    # fallo de restauración interrumpa la reversión en vez de pasar
    # desapercibido (antes: --archivo, que ni existe, con check=False).
    subprocess.run(
        [str(python), str(ROOT / "tools" / "restore_backup.py"), zip_path,
         "--config", args.config, "--database", rollback_db],
        check=True)
    rc = _run_odoo(args.config, rollback_db, "--stop-after-init", "--no-http")
    if rc != 0:
        raise RuntimeError(
            "La copia restaurada (%s) no arranca con el código anterior; "
            "no se activa. La base %s NO se ha tocado." % (rollback_db, args.database))
    quarantine = _swap_databases(args.config, args.database, rollback_db)
    return quarantine


def _swap_databases(config, database, replacement):
    """Cambio atómico de qué base ocupa `database`: la migrada (con
    problemas) pasa a un nombre de cuarentena y la restaurada la sustituye.
    Requiere que nadie esté conectado a ninguna de las dos (el servicio debe
    estar parado a estas alturas del rollback)."""
    sys.path.insert(0, str(ROOT / "odoo"))
    import odoo
    odoo.tools.config.parse_config(["-c", str(config), "--no-http"])
    for name in (database, replacement):
        odoo.sql_db.close_db(name)
    quarantine = "%s_migrada_%s" % (database, datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    with odoo.sql_db.db_connect("postgres").cursor() as cr:
        cr.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = ANY(%s) AND pid <> pg_backend_pid()",
            [[database, replacement]])
        cr.execute('ALTER DATABASE "%s" RENAME TO "%s"' % (database, quarantine))
        cr.execute('ALTER DATABASE "%s" RENAME TO "%s"' % (replacement, database))
        cr.commit()
    odoo.sql_db.close_db("postgres")
    return quarantine


def _applied_version(odoo, database):
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute("SELECT latest_version FROM ir_module_module WHERE name = 'mi_gestor_stock'")
        row = cr.fetchone()
    return row[0] if row else None


def _clear_maintenance(odoo, database):
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute("DELETE FROM ir_config_parameter WHERE key = 'mgs.maintenance'")
        cr.commit()


# Unidad de versión completa (hallazgo 10). Antes solo se instalaba
# _BASE_UNIT aunque el manifiesto declarase incluye_motor=true: odoo-
# revision.txt cambiaba pero el motor y el venv seguían siendo los antiguos,
# y el servicio dejaba de arrancar (service_process.py rechaza una revisión
# que no coincide). _BASE_UNIT siempre viaja; _ENGINE_UNIT solo si el
# manifiesto trae motor propio.
_BASE_UNIT = ("custom_addons", "tools", "odoo-revision.txt", "requirements-windows.lock")
_ENGINE_UNIT = ("odoo", "python", "wheels", "instalador",
                "bootstrap.ps1", "start-odoo.ps1", "install-pdf.ps1",
                "preparar-equipo.ps1", "restore-backup.ps1", "reset-catalogo.ps1",
                "service.ps1", "recuperar-acceso.ps1", "diagnostico.ps1", "test.ps1",
                "odoo.conf", "integridad.json", "integridad.json.sig")
_FULL_UNIT = _BASE_UNIT + _ENGINE_UNIT


def _version_unit(manifest):
    """Componentes a instalar según declare el manifiesto. Con
    incluye_motor=false, compat_problems() ya exige que la revisión Odoo
    instalada coincida con la que pide el paquete, así que basta la base."""
    if manifest and manifest.get("incluye_motor"):
        return _FULL_UNIT
    return _BASE_UNIT


def _copy_component(source, target):
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _snapshot_code(src, dst):
    """Respaldo del código ANTES de aplicar: se guarda todo lo que exista de
    la unidad completa, exista o no en el manifiesto entrante — es una foto
    de lo que hay instalado ahora, no de lo que se va a instalar."""
    dst.mkdir(parents=True, exist_ok=True)
    for name in _FULL_UNIT:
        source = Path(src) / name
        if source.exists():
            _copy_component(source, dst / name)


def _restore_code(snapshot, dst):
    """Reversión: repone exactamente lo que el respaldo capturó (existencia
    por componente, igual que _snapshot_code)."""
    for name in _FULL_UNIT:
        source = snapshot / name
        if source.exists():
            _copy_component(source, Path(dst) / name)


def _install_package(zip_path, dst, manifest):
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        payload = Path(tmp)
        inner = [p for p in payload.iterdir() if p.is_dir()]
        if len(inner) == 1 and not (payload / "custom_addons").exists():
            payload = inner[0]
        unit = _version_unit(manifest)
        if manifest and manifest.get("incluye_motor"):
            # Solo se exige lo sustancial (motor, intérprete, ruedas,
            # instalador): los lanzadores .ps1 sueltos y los ficheros de
            # integridad son parte de la unidad pero no lo que define si el
            # paquete "trae motor propio" de verdad.
            criticos = ("odoo", "python", "wheels", "instalador")
            faltan = [name for name in criticos if not (payload / name).exists()]
            if faltan:
                raise RuntimeError(
                    "El manifiesto declara incluye_motor=true pero el paquete no "
                    "trae: %s" % ", ".join(faltan))
        for name in unit:
            source = payload / name
            if source.exists():
                _copy_component(source, Path(dst) / name)


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
