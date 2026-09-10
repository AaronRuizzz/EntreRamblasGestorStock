"""Compara dos diagnósticos (tools/diagnostico.py) y enseña sólo las diferencias.

    python tools/comparar_diagnosticos.py equipo-a.json equipo-b.json

Ignora campos que SIEMPRE difieren (fecha, nombre de base). Sirve para la
prueba de reproducibilidad del plan: una base nueva frente a una actualizada.
"""
import argparse
import json
import sys

_IGNORE = {"generado", "base_datos"}


def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if prefix == "" and key in _IGNORE:
                continue
            out.update(_flatten(value, prefix + key + "."))
    elif isinstance(obj, list):
        # listas de módulos: {nombre: version}; el resto, por índice
        if obj and isinstance(obj[0], dict) and "nombre" in obj[0]:
            for item in obj:
                out[prefix + item["nombre"]] = item.get("version")
        else:
            for i, item in enumerate(obj):
                out.update(_flatten(item, prefix + str(i) + "."))
    else:
        out[prefix.rstrip(".")] = obj
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a")
    parser.add_argument("b")
    args = parser.parse_args()
    a = _flatten(json.load(open(args.a, encoding="utf-8")))
    b = _flatten(json.load(open(args.b, encoding="utf-8")))
    keys = sorted(set(a) | set(b))
    diffs = [(k, a.get(k, "—(falta)"), b.get(k, "—(falta)")) for k in keys if a.get(k) != b.get(k)]
    if not diffs:
        print("Sin diferencias relevantes.")
        return 0
    width = max(len(k) for k, _, _ in diffs)
    print("%-*s  %-28s  %s" % (width, "campo", args.a, args.b))
    for key, va, vb in diffs:
        print("%-*s  %-28s  %s" % (width, key, va, vb))
    return 1


if __name__ == "__main__":
    sys.exit(main())
