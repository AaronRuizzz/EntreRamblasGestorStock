# -*- coding: utf-8 -*-
r"""Verifica que el entorno Python de la aplicación es propio y no depende del
PC del desarrollador.

El empaquetador dejaba `venv/` tal cual, con `pyvenv.cfg` apuntando a
`C:\Users\<dev>\AppData\Local\Programs\Python\Python312`. En un Windows sin ese
Python ni ese perfil, `venv\Scripts\python.exe` no arranca. Ahora el paquete
trae su propio CPython bajo `<raíz>\python` y el instalador construye el venv en
destino; este script comprueba el resultado.

Comprueba:
  * la versión de Python es 3.12;
  * `sys.base_prefix` (el Python base del venv) está DENTRO del árbol de la
    aplicación, no en un perfil de usuario;
  * `pyvenv.cfg` no apunta a rutas de otro perfil;
  * todos los paquetes de `requirements-windows.lock` están instalados con la
    versión exacta fijada.

Códigos de salida (mismo criterio que verificar_motor.py):
  0  entorno propio y completo
  2  la versión de Python no es 3.12
  3  el Python base está fuera de la app, pyvenv.cfg apunta a otro perfil, o
     faltan/di­fieren paquetes del lock
  4  no se pudo comprobar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements-windows.lock"
PYVENV = ROOT / "venv" / "pyvenv.cfg"


def _read_lock():
    pins = []
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, version = line.partition("==")
        pins.append((name.strip(), version.strip()))
    return pins


def _installed_version(name):
    from importlib import metadata
    for candidate in (name, name.replace("-", "_"), name.replace("_", "-"),
                      name.lower(), name.lower().replace("-", "_")):
        try:
            return metadata.version(candidate)
        except metadata.PackageNotFoundError:
            continue
    return None


def _under_root(path_str):
    try:
        return Path(path_str).resolve().is_relative_to(ROOT)
    except (OSError, ValueError):
        return False


def check() -> dict:
    result = {"ok": False, "code": 4, "estado": "sin-comprobar", "detalles": []}

    py = sys.version_info[:2]
    result["python"] = "%d.%d.%d" % sys.version_info[:3]
    result["base_prefix"] = sys.base_prefix
    version_ok = py == (3, 12)

    base_ok = _under_root(sys.base_prefix)
    if not base_ok:
        result["detalles"].append(
            "El Python base del venv está fuera de la aplicación: %s" % sys.base_prefix)

    pyvenv_ok = True
    if PYVENV.is_file():
        cfg = {}
        for line in PYVENV.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip().lower()] = v.strip()
        result["pyvenv_home"] = cfg.get("home", "")
        for key in ("home", "executable", "command"):
            value = cfg.get(key, "")
            if not value:
                continue
            token = value.split(" -m ", 1)[0].strip() if key == "command" else value
            if token and not _under_root(token):
                pyvenv_ok = False
                result["detalles"].append("pyvenv.cfg %s fuera de la aplicación: %s" % (key, token))
    else:
        result["detalles"].append("No hay venv/pyvenv.cfg")
        pyvenv_ok = False

    missing, mismatched = [], []
    try:
        for name, pinned in _read_lock():
            got = _installed_version(name)
            if got is None:
                missing.append(name)
            elif got != pinned:
                mismatched.append("%s: %s (se esperaba %s)" % (name, got, pinned))
    except OSError:
        result["detalles"].append("No se pudo leer requirements-windows.lock")
        return result
    result["paquetes_ausentes"] = missing
    result["paquetes_distintos"] = mismatched
    result["detalles"].extend("falta %s" % n for n in missing)
    result["detalles"].extend(mismatched)

    packages_ok = not missing and not mismatched
    intacto = version_ok and base_ok and pyvenv_ok and packages_ok
    if not version_ok:
        code = 2
    elif not intacto:
        code = 3
    else:
        code = 0
    result.update(ok=intacto, code=code,
                  estado="intacto" if intacto else ("python-distinto" if not version_ok else "incompleto"))
    return result


def _texto(result: dict) -> str:
    if result["code"] == 0:
        return "intacto Python %s (base en la app)" % result.get("python")
    if result["code"] == 2:
        return "python-distinto: %s (se requiere 3.12)" % result.get("python")
    if result["code"] == 4:
        return "sin-comprobar: " + "; ".join(result.get("detalles") or ["?"])
    return "incompleto:\n" + "\n".join("  " + d for d in result.get("detalles") or [])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verifica el entorno Python de la aplicación.")
    ap.add_argument("--json", action="store_true", help="detalle estructurado")
    args = ap.parse_args(argv)
    result = check()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _texto(result))
    return result["code"]


if __name__ == "__main__":
    sys.exit(main())
