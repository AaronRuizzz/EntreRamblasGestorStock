# -*- coding: utf-8 -*-
r"""Verifica la integridad del motor Odoo fijado por el proyecto.

Va mas alla del identificador de commit: comprueba que ningun fichero
VERSIONADO del motor se haya modificado, anadido o renombrado respecto al
commit fijado (`odoo-revision.txt`), y que los ficheros que intervienen en la
ejecucion esten presentes en disco. Un parche a mano sobre `odoo/` no cambia
el commit pero rompe la igualdad de comportamiento entre equipos: eso es lo
que hay que detectar.

Tolera, sin bloquear el arranque:
  * la AUSENCIA de ficheros que no intervienen en la ejecucion: documentacion
    (`doc/`), empaquetado (`debian/`, `setup/`), ficheros de datos de pruebas
    (`addons/*/tests/`), metadatos de licencia. En un equipo de tienda es
    habitual no tenerlos, y su ausencia no cambia como se ejecuta Odoo.
  * las "bajas fantasma": ficheros que git cree borrados pero siguen en disco
    y con el contenido del commit (tipico de OneDrive evacuando carpetas frias
    y un `git add` posterior).
  * los ficheros sin versionar (`__pycache__`, `*.pyc`, ...).

Salida de texto (una linea) y codigo de salida:
  0  intacto (quiza con aviso: faltan ficheros no ejecutables)
  2  el commit no coincide con odoo-revision.txt
  3  hay ficheros versionados modificados/anadidos, o faltan ficheros de
     ejecucion del motor
  4  no se pudo ejecutar git

Con `--json` imprime el detalle estructurado (lo usa el diagnostico).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

# tools/ -> EntreRamblas
ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "odoo"
PIN_FILE = ROOT / "odoo-revision.txt"

# Distribución instalada (sin Git): el empaquetador firmado deja un mapa
# ruta -> sha256 y su firma Ed25519. Es el modo que usa la tienda.
DIST_MANIFEST = ROOT / "integridad.json"
DIST_SIG = ROOT / "integridad.json.sig"
PUBLIC_KEY = ROOT / "instalador" / "firma-publica.pem"

# Ficheros imprescindibles para arrancar. Si faltan, el checkout esta roto
# aunque el commit coincida.
ENTRYPOINTS = (
    "odoo-bin",
    "odoo/__init__.py",
    "odoo/release.py",
    "odoo/http.py",
    "odoo/service/server.py",
    "odoo/modules/module.py",
    "odoo/addons/base/__manifest__.py",
    "odoo/addons/base/models/ir_module.py",
)

# Subcarpetas de un addon cuyo contenido influye en como se ejecuta Odoo.
_RUNTIME_ADDON_DIRS = frozenset((
    "models", "controllers", "views", "data", "security", "report",
    "wizard", "wizards", "static", "populate", "i18n",
))


def _git(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["git", "-C", str(ENGINE), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _is_runtime_path(path: str) -> bool:
    """True si la presencia/contenido del fichero cambia como se ejecuta Odoo."""
    if path.startswith("odoo/"):
        # el paquete Python del motor; sus pruebas no intervienen en ejecucion
        return "/tests/" not in path
    if path.startswith("addons/"):
        parts = path.split("/")
        if len(parts) < 3:
            return False
        if parts[2] == "tests":
            return False
        if parts[2] in ("__init__.py", "__manifest__.py"):
            return True
        return parts[2] in _RUNTIME_ADDON_DIRS
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_from_hashes() -> dict:
    """Integridad de una distribución instalada: firma Ed25519 del mapa de
    hashes + recálculo de cada fichero. No necesita Git."""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        from paquete_firma import load_public, verify_bytes
    except ImportError:
        return {"ok": False, "code": 4, "estado": "sin-comprobar", "modo": "hashes",
                "detalle": "falta tools/paquete_firma.py"}

    try:
        raw = DIST_MANIFEST.read_bytes()
        signature = DIST_SIG.read_text(encoding="ascii").strip()
    except OSError as exc:
        return {"ok": False, "code": 4, "estado": "sin-comprobar", "modo": "hashes",
                "detalle": "no se pudo leer integridad.json(.sig): %s" % exc}

    firma_valida = PUBLIC_KEY.is_file() and verify_bytes(
        load_public(PUBLIC_KEY), raw, signature)
    if not firma_valida:
        return {"ok": False, "code": 3, "estado": "modificado", "modo": "hashes",
                "firma_valida": False, "ficheros_modificados": ["integridad.json"],
                "ficheros_ejecucion_ausentes": [], "ficheros_ejecucion_borrados": [],
                "detalle": "la firma de integridad.json no es válida"}

    manifest = json.loads(raw.decode("utf-8"))
    pinned = None
    try:
        pinned = PIN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    declared_rev = manifest.get("odoo_revision")
    revision_ok = bool(declared_rev and pinned and declared_rev == pinned)

    modificados: list[str] = []
    ausentes: list[str] = []
    for rel, expected in sorted(manifest.get("ficheros", {}).items()):
        target = ROOT / rel
        if not target.is_file():
            ausentes.append(rel)
        elif _sha256(target) != expected:
            modificados.append(rel)

    faltan_ejecucion = [p for p in ausentes if _is_runtime_path(_engine_relative(p))]
    intacto = revision_ok and not modificados and not faltan_ejecucion
    return {
        "ok": intacto,
        "code": 0 if intacto else (2 if not revision_ok and not modificados and not faltan_ejecucion else 3),
        "estado": "intacto" if intacto else ("revision-distinta" if not revision_ok else "modificado"),
        "modo": "hashes",
        "firma_valida": True,
        "revision_fijada": pinned,
        "revision_actual": declared_rev,
        "revision_coincide": revision_ok,
        "ficheros_modificados": modificados,
        "ficheros_ejecucion_ausentes": faltan_ejecucion,
        "ficheros_ejecucion_borrados": [],
        "ficheros_no_ejecucion_ausentes": len([p for p in ausentes if p not in faltan_ejecucion]),
        "bajas_fantasma": 0,
    }


def _engine_relative(rel: str) -> str:
    """`_is_runtime_path` razona en rutas relativas a odoo/ (odoo/… o addons/…).
    El mapa de integridad las guarda relativas a la raíz (odoo/odoo/…, odoo/addons/…)."""
    if rel.startswith("odoo/odoo/"):
        return rel[len("odoo/"):]
    if rel.startswith("odoo/addons/"):
        return rel[len("odoo/"):]
    return rel


def check() -> dict:
    if not (ENGINE / ".git").exists() and DIST_MANIFEST.is_file():
        return _check_from_hashes()

    try:
        pinned = PIN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        pinned = None

    head = _git("rev-parse", "HEAD")
    if head is None or head.returncode != 0:
        detail = (head.stderr.strip() if head else "git no disponible")
        return {"ok": False, "code": 4, "estado": "sin-git", "detalle": detail}

    current = head.stdout.strip()
    revision_ok = bool(pinned and current == pinned)

    names = _git("diff", "--name-status", "-z", "HEAD")
    if names is None or names.returncode != 0:
        detail = (names.stderr.strip() if names else "git no disponible")
        return {"ok": False, "code": 4, "estado": "sin-git", "detalle": detail}

    modificados: list[str] = []
    borrados: list[str] = []
    fields = names.stdout.split("\0")
    i = 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        if status[0] in ("R", "C"):  # rename/copy: status, origen, destino
            if i + 2 < len(fields):
                modificados.extend([fields[i + 1], fields[i + 2]])
            i += 3
            continue
        if i + 1 >= len(fields):
            break
        path = fields[i + 1]
        i += 2
        if status[0] == "D":
            borrados.append(path)
        else:  # A, M, T, U, X, B
            modificados.append(path)

    faltan_ejecucion = [p for p in ENTRYPOINTS if not (ENGINE / p).exists()]
    # "borrado" real = git lo da por borrado Y no esta en disco.
    borrados_reales = [p for p in borrados if not (ENGINE / p).exists()]
    borrados_ejecucion = sorted(p for p in borrados_reales if _is_runtime_path(p))
    borrados_no_ejecucion = [p for p in borrados_reales if not _is_runtime_path(p)]
    fantasma = [p for p in borrados if (ENGINE / p).exists()]

    intacto = (
        revision_ok
        and not modificados
        and not faltan_ejecucion
        and not borrados_ejecucion
    )
    if not revision_ok:
        code = 2
    elif not intacto:
        code = 3
    else:
        code = 0

    return {
        "ok": intacto,
        "code": code,
        "estado": "intacto" if intacto else ("revision-distinta" if not revision_ok else "modificado"),
        "modo": "git",
        "revision_fijada": pinned,
        "revision_actual": current,
        "revision_coincide": revision_ok,
        "ficheros_modificados": sorted(modificados),
        "ficheros_ejecucion_ausentes": list(faltan_ejecucion),
        "ficheros_ejecucion_borrados": borrados_ejecucion,
        "ficheros_no_ejecucion_ausentes": len(borrados_no_ejecucion),
        "bajas_fantasma": len(fantasma),
    }


def _texto(result: dict) -> str:
    code = result["code"]
    if code == 0:
        msg = "intacto %s" % (result.get("revision_actual") or "?")
        extra = []
        if result.get("ficheros_no_ejecucion_ausentes"):
            extra.append("faltan %d ficheros no ejecutables (documentacion/empaquetado/pruebas)"
                         % result["ficheros_no_ejecucion_ausentes"])
        if result.get("bajas_fantasma"):
            extra.append("%d bajas fantasma en el indice (inofensivo)" % result["bajas_fantasma"])
        if extra:
            msg += " [" + "; ".join(extra) + "]"
        return msg
    if code == 2:
        return ("revision-distinta actual=%s fijada=%s"
                % (result.get("revision_actual"), result.get("revision_fijada")))
    if code == 4:
        return ("sin-git %s" % result.get("detalle", "")).strip()
    partes = []
    if result["ficheros_modificados"]:
        partes.append("%d modificados/anadidos" % len(result["ficheros_modificados"]))
    if result["ficheros_ejecucion_ausentes"]:
        partes.append("%d de ejecucion ausentes" % len(result["ficheros_ejecucion_ausentes"]))
    if result["ficheros_ejecucion_borrados"]:
        partes.append("%d de ejecucion borrados" % len(result["ficheros_ejecucion_borrados"]))
    lineas = ["modificado " + ", ".join(partes)]
    muestra = (result["ficheros_modificados"][:10]
               + result["ficheros_ejecucion_ausentes"][:10]
               + result["ficheros_ejecucion_borrados"][:10])
    lineas += ["  " + p for p in muestra]
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verifica la integridad del motor Odoo.")
    ap.add_argument("--json", action="store_true", help="detalle estructurado")
    args = ap.parse_args(argv)
    result = check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_texto(result))
    return result["code"]


if __name__ == "__main__":
    sys.exit(main())
