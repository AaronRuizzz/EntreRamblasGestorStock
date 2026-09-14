# -*- coding: utf-8 -*-
"""Comprueba que un manifiesto publicado lo lee EXACTAMENTE el mismo código del
actualizador: sin BOM, UTF-8 válido y JSON con las claves mínimas.

PowerShell 5.1 escribe `Set-Content -Encoding utf8` con BOM; `actualizador.py`
hace `json.loads(raw.decode('utf-8'))` y revienta con «Unexpected UTF-8 BOM».
Este control lo caza antes de firmar y publicar.
"""
import argparse
import json
import sys
from pathlib import Path

REQUIRED = ("version", "archivo", "sha256")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archivo", required=True)
    args = ap.parse_args(argv)

    raw = Path(args.archivo).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        print("ERROR: el manifiesto empieza con BOM UTF-8; el actualizador no lo lee.",
              file=sys.stderr)
        return 1
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print("ERROR: el manifiesto no es UTF-8 válido: %s" % exc, file=sys.stderr)
        return 1
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print("ERROR: el manifiesto no es JSON válido: %s" % exc, file=sys.stderr)
        return 1
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        print("ERROR: faltan claves en el manifiesto: %s" % ", ".join(missing), file=sys.stderr)
        return 1
    print("OK: manifiesto legible por el actualizador (sin BOM, JSON válido)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
