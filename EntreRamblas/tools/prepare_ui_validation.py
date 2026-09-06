"""Datos de demostración exclusivamente en PostgreSQL de pruebas (55432)."""
import json
import secrets
import sys
from datetime import timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "odoo"))
import odoo
from odoo import api, Command, fields, SUPERUSER_ID
from odoo.modules.registry import Registry

odoo.tools.config.parse_config(["-c", str(root / "odoo.conf"), "--db_host=127.0.0.1",
                              "--db_port=55432", "--db_user=mgs_test", "-d", "mgs_validation"])
with Registry("mgs_validation").cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {"no_reset_password": True, "mail_create_nosubscribe": True})
    company = env.company
    if not company.chart_template:
        company.write({"country_id": env.ref("base.es").id, "currency_id": env.ref("base.EUR").id})
        env["account.chart.template"].try_loading("es_pymes", company)
    credentials = {}
    for role, group in [("owner", "group_mgs_manager"), ("staff", "group_mgs_user")]:
        login = "mgs_ui_" + role
        user = env["res.users"].search([("login", "=", login)], limit=1)
        password = secrets.token_urlsafe(24)
        values = {"name": "Prueba " + role, "login": login, "password": password,
                  "email": login + "@example.invalid",
                  "groups_id": [Command.set([env.ref("mi_gestor_stock." + group).id])],
                  "company_id": company.id, "company_ids": [Command.set([company.id])],
                  "lang": "es_ES", "tz": "Europe/Madrid"}
        if user:
            user.write(values)
        else:
            user = env["res.users"].create(values)
        credentials[role] = {"login": login, "password": password}
    config = env["pos.config"].search([("name", "=", "TPV prueba floristería")], limit=1)
    if not config:
        config = env["pos.config"].create({"name": "TPV prueba floristería", "iface_print_auto": True,
                                           "iface_cashdrawer": True})
    credentials["pos_config_id"] = config.id
    credentials["database"] = "mgs_validation"
    hardware = env["mgs.config"]._mgs_get()
    hardware.write({"printer_mode": "path", "printer_path": str(root / ".odoo_data" / "ui-printer.bin"),
                    "pos_autoprint": True, "backup_enabled": False})
    for code, name, price in [("MGS-UI-ROSA", "Rosa roja · prueba", 5), ("MGS-UI-JARRON", "Jarrón · prueba", 12)]:
        product = env["product.product"].search([("barcode", "=", code)], limit=1)
        if not product:
            product = env["product.product"].create({"name": name, "barcode": code, "list_price": price,
                "standard_price": price / 2, "tracking": "lot", "mgs_auto_lots": True, "use_expiration_date": True,
                "is_storable": True, "available_in_pos": True})
            for days, quantity in [(2, 10), (6, 15)]:
                reception = env["mgs.reception"].create({"line_ids": [Command.create({
                    "product_id": product.id, "quantity": quantity, "unit_cost": price / 2,
                    "expiry_date": fields.Date.today() + timedelta(days=days),
                })]})
                reception.action_confirm()
    cr.commit()
    path = root / ".odoo_data" / "ui-validation.json"
    path.write_text(json.dumps(credentials), encoding="utf-8")
    print("Datos de prueba preparados; credenciales locales en", path)
