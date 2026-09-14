# -*- coding: utf-8 -*-
"""Genera `integridad.json`: mapa ruta-relativa -> sha256 de todo el código que
viaja en el paquete de la tienda (motor Odoo, addons, tools, instalador y los
scripts de arranque). El empaquetador lo firma con la clave Ed25519.

La tienda no tiene Git: `tools/verificar_motor.py` comprueba la firma de este
archivo y recalcula cada hash para detectar cualquier manipulación del código
instalado, con el mismo criterio que el arranque en desarrollo.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Carpetas cuyo contenido íntegro se sella.
TREE_ROOTS = ("odoo", "custom_addons", "tools", "instalador")
# Ficheros sueltos de la raíz.
LOOSE_FILES = (
    "odoo-revision.txt", "requirements-windows.lock", "odoo.conf",
    "bootstrap.ps1", "start-odoo.ps1", "install-pdf.ps1", "preparar-equipo.ps1",
    "restore-backup.ps1", "reset-catalogo.ps1", "service.ps1",
    "recuperar-acceso.ps1", "diagnostico.ps1", "test.ps1",
)
EXCLUDE_DIRS = {"__pycache__", ".git", ".pytest_cache", ".odoo_data", "sessions",
                "filestore", "wkhtmltox", "node_modules"}
EXCLUDE_SUFFIX = (".pyc", ".pyo", ".log", ".err", ".7z", ".secret")
EXCLUDE_NAMES = {"integridad.json", "integridad.json.sig", "odoo.local",
                 "odoo.local.pending"}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk(base):
    for path in sorted(base.rglob("*")):
        if path.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(base).parts):
            continue
        if path.name in EXCLUDE_NAMES or path.suffix.lower() in EXCLUDE_SUFFIX:
            continue
        yield path


def build(root):
    root = Path(root).resolve()
    files = {}
    for name in TREE_ROOTS:
        base = root / name
        if not base.is_dir():
            continue
        for path in _walk(base):
            files[path.relative_to(root).as_posix()] = _sha256(path)
    for name in LOOSE_FILES:
        path = root / name
        if path.is_file():
            files[name] = _sha256(path)
    revision = ""
    rev_file = root / "odoo-revision.txt"
    if rev_file.is_file():
        revision = rev_file.read_text(encoding="utf-8").strip()
    return {
        "odoo_revision": revision,
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ficheros": files,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--salida", default=str(ROOT / "integridad.json"))
    args = ap.parse_args(argv)
    data = build(args.root)
    Path(args.salida).write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    print("integridad.json: %d ficheros -> %s" % (len(data["ficheros"]), args.salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
