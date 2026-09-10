r"""Vuelca el diagnóstico de la instalación a un JSON, sin secretos.

Sirve para comparar dos equipos: ejecutar en cada uno y comparar los archivos.

    .\venv\Scripts\python.exe tools\diagnostico.py --config <odoo.local> --database <base> [--salida ruta.json]
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "odoo"))
import odoo  # noqa: E402
from odoo import api, SUPERUSER_ID  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--salida", help="Archivo de destino (por defecto, junto al config)")
    args = parser.parse_args()
    odoo.tools.config.parse_config(["-c", args.config, "-d", args.database, "--no-http"])

    with Registry(args.database).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        text = env["mgs.diagnostic"]._gather_text()

    if args.salida:
        target = Path(args.salida)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        target = Path(args.config).parent / f"diagnostico-{args.database}-{stamp}.json"
    target.write_text(text, encoding="utf-8")
    print("Diagnóstico guardado en", target)


if __name__ == "__main__":
    main()
