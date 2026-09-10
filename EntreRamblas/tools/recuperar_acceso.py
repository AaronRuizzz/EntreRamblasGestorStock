r"""Recuperación local del acceso — para cuando se pierden la contraseña Y la
clave de recuperación.

Requiere ejecutarse como **administrador de Windows** (lo comprueba). No usa
ninguna contraseña maestra compartida: lo que hace es dejar el **primer acceso
otra vez pendiente**, con un código de activación nuevo, para que la dueña
vuelva a elegir su contraseña y reciba una clave de recuperación nueva desde
`/mgs/primer-acceso`. Cada uso queda registrado en el rastro de
restablecimientos (`mgs.access.event`).

Uso (desde la carpeta EntreRamblas, PowerShell como administrador):

    .\venv\Scripts\python.exe tools\recuperar_acceso.py activar --config <odoo.local> --database <base>
    .\venv\Scripts\python.exe tools\recuperar_acceso.py admin   --config <odoo.local> --database <base>

`activar` reinicia el primer acceso de la propietaria (lo normal).
`admin`   restablece la contraseña de la cuenta técnica `admin` (mantenimiento
          profundo); la enseña una sola vez.
"""
import argparse
import ctypes
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "odoo"))
import odoo  # noqa: E402
from odoo import api, SUPERUSER_ID  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402


def _require_windows_admin():
    if os.name != "nt":
        raise SystemExit("Esta herramienta está pensada para el PC de la tienda (Windows).")
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:  # noqa: BLE001
        is_admin = 0
    if not is_admin:
        raise SystemExit(
            "Ejecuta esta herramienta desde una consola abierta como "
            "administrador (clic derecho -> «Ejecutar como administrador»).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["activar", "admin"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", args.database):
        raise SystemExit("Nombre de base no válido.")

    _require_windows_admin()
    odoo.tools.config.parse_config(["-c", args.config, "-d", args.database, "--no-http"])

    with Registry(args.database).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {"no_reset_password": True})
        access = env["mgs.access"].sudo()
        owner = env["res.users"].sudo()._mgs_owner()
        if not owner:
            raise SystemExit("Esta base no tiene ninguna cuenta de propietaria configurada.")

        if args.operation == "admin":
            import secrets
            admin = env.ref("base.user_admin")
            password = secrets.token_urlsafe(18)
            admin.write({"login": "admin", "password": password})
            access._log_event(
                "herramienta-local",
                "Contraseña de la cuenta técnica «admin» restablecida con la herramienta local.")
            cr.commit()
            print("\n  Cuenta técnica: admin")
            print("  Contraseña (solo se muestra ahora): " + password + "\n")
            return

        code = access._begin_activation(owner)
        access._log_event(
            "herramienta-local",
            "Primer acceso reiniciado con la herramienta local; código de activación nuevo.")
        cr.commit()

    target = Path(args.config).parent / (args.database + "-activacion.txt")
    try:
        target.write_text(
            "Codigo de activacion (recuperacion local)\n"
            "Base de datos: " + args.database + "\n"
            "Generado: " + datetime.now().isoformat(timespec="seconds") + "\n\n"
            "    " + code + "\n\n"
            "En la pantalla de primer acceso, escribe este codigo y elige una\n"
            "contrasena nueva. Guarda despues la clave de recuperacion.\n",
            encoding="utf-8")
        print("\n  Primer acceso reiniciado. Código de activación en:\n  " + str(target) + "\n")
    except OSError:
        print("\n  Primer acceso reiniciado. Código de activación:\n\n    " + code + "\n")


if __name__ == "__main__":
    main()
