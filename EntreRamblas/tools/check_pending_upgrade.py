"""¿El código del módulo es más nuevo que lo aplicado a la base?

Imprime una sola palabra:
  current  — la base ya está a la versión del código
  upgrade  — hay que ejecutar `-u mi_gestor_stock` antes de servir
  unknown  — el módulo no está instalado o la base no responde

Lo usa start-odoo.ps1 para lanzar la actualización controlada en un arranque
normal (Odoo, sin `-u`, no migra aunque el código haya cambiado).
"""
import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "odoo"))
import odoo  # noqa: E402

MANIFEST = ROOT / "custom_addons" / "mi_gestor_stock" / "__manifest__.py"


def _manifest_version():
    return ast.literal_eval(MANIFEST.read_text(encoding="utf-8"))["version"]


def _norm(version):
    version = (version or "").strip()
    parts = version.split(".")
    # Odoo guarda siempre la serie delante ("18.0.x.y.z"); el manifiesto puede
    # no llevarla. Se comparan las últimas tres cifras (x.y.z del módulo).
    return ".".join(parts[-3:]) if len(parts) >= 3 else version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    odoo.tools.config.parse_config(["-c", args.config, "-d", args.database, "--no-http"])
    try:
        with odoo.sql_db.db_connect(args.database).cursor() as cr:
            cr.execute(
                "SELECT latest_version, state FROM ir_module_module WHERE name = %s",
                ["mi_gestor_stock"])
            row = cr.fetchone()
    except Exception:  # noqa: BLE001 - la base puede no existir todavía
        print("unknown")
        return
    if not row or row[1] != "installed":
        print("unknown")
        return
    print("current" if _norm(row[0]) == _norm(_manifest_version()) else "upgrade")


if __name__ == "__main__":
    main()
