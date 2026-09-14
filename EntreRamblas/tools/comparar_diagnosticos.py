"""Compara dos diagnósticos (tools/diagnostico.py) y enseña sólo las diferencias.

    python tools/comparar_diagnosticos.py equipo-a.json equipo-b.json

Ignora campos que SIEMPRE difieren (fecha, nombre de base) y el historial de
versiones aplicadas (fechas de instalación de cada equipo, que nunca
coinciden entre una base nueva y una migrada aunque ejecuten exactamente lo
mismo). Compara lo que sí define el comportamiento: versión aplicada,
módulos, permisos y configuración. Sirve para la prueba de reproducibilidad
del plan: una base nueva frente a una actualizada.
"""
import argparse
import json
import sys

_IGNORE = {"generado", "base_datos"}
# Campos informativos que NO rompen la igualdad de comportamiento entre equipos:
# un equipo puede tener menos documentación o ficheros de prueba del motor (o
# bajas fantasma en el índice de git) y ejecutar exactamente el mismo código.
_IGNORE_KEYS = {
    "motor_odoo.ficheros_no_ejecucion_ausentes",
    "motor_odoo.bajas_fantasma",
}
# Subárboles que se muestran como información pero NUNCA cuentan como
# diferencia: el historial trae la fecha de cada instalación/actualización,
# que por diseño es distinta entre una base nueva y una migrada aunque el
# resultado final (modulo.aplicado, más abajo) sea idéntico.
_IGNORE_SUBTREES = ("modulo.historico_versiones",)


def _ignored_subtree(path):
    return any(path == subtree or path.startswith(subtree + ".") for subtree in _IGNORE_SUBTREES)


def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            if prefix == "" and key in _IGNORE:
                continue
            path = prefix + key
            if _ignored_subtree(path):
                continue
            out.update(_flatten(value, path + "."))
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


def _history_summary(data):
    history = (data.get("modulo") or {}).get("historico_versiones") or []
    if not history:
        return "(sin historial)"
    return ", ".join("%s (%s)" % (h.get("version"), h.get("aplicada")) for h in history)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("a")
    parser.add_argument("b")
    args = parser.parse_args()
    raw_a = json.load(open(args.a, encoding="utf-8"))
    raw_b = json.load(open(args.b, encoding="utf-8"))
    a = _flatten(raw_a)
    b = _flatten(raw_b)
    keys = sorted((set(a) | set(b)) - _IGNORE_KEYS)
    diffs = [(k, a.get(k, "—(falta)"), b.get(k, "—(falta)")) for k in keys if a.get(k) != b.get(k)]

    print("Historial (informativo, no cuenta como diferencia):")
    print("  %s: %s" % (args.a, _history_summary(raw_a)))
    print("  %s: %s" % (args.b, _history_summary(raw_b)))
    print()

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
