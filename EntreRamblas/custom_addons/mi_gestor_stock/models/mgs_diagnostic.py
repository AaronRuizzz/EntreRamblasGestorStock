# -*- coding: utf-8 -*-
"""Diagnóstico exportable, sin secretos, para comparar dos instalaciones.

Reúne: versión del módulo (código vs. aplicada), revisión e integridad del
motor Odoo, configuración común (idioma, zona, moneda, país, plan contable,
caja de tienda, menús ocultos, registro público, acceso de la propietaria) y
la lista de módulos instalados con su versión. **No incluye** contraseñas,
claves, rutas privadas, NIF, ni datos de tienda.
"""
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from odoo import _, api, fields, models
from odoo.modules.module import get_manifest

_logger = logging.getLogger(__name__)

# custom_addons/mi_gestor_stock/models/ -> .../EntreRamblas
_RUNTIME_ROOT = Path(__file__).resolve().parents[3]

_NATIVE_ROOT_MENUS = [
    "mail.menu_root_discuss", "contacts.menu_contacts",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
    "point_of_sale.menu_point_root", "account.menu_finance",
    "stock.menu_stock_root", "base.menu_management", "base.menu_tests",
    "base.menu_administration",
]


def _git(cwd, *args):
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True, text=True, timeout=15, check=False)
        return done
    except (OSError, subprocess.SubprocessError):
        return None


def _module_tail(version):
    parts = (version or "").split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 else (version or "")


class MgsDiagnostic(models.TransientModel):
    _name = "mgs.diagnostic"
    _description = "Diagnóstico de instalación"

    report_text = fields.Text(readonly=True)

    @api.model
    def _gather(self):
        env = self.env
        data = {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base_datos": env.cr.dbname,
        }
        for key, fn in (
            ("modulo", self._section_module),
            ("motor_odoo", self._section_engine),
            ("config_comun", self._section_common_config),
            ("modulos_instalados", self._section_modules),
        ):
            try:
                data[key] = fn()
            except Exception as err:  # noqa: BLE001 - un diagnóstico nunca revienta
                _logger.exception("mi_gestor_stock: diagnóstico, sección %s", key)
                data[key] = {"error": str(err)}
        return data

    def _section_module(self):
        module = self.env["ir.module.module"].sudo().search(
            [("name", "=", "mi_gestor_stock")], limit=1)
        code_version = get_manifest("mi_gestor_stock").get("version")
        try:
            history = json.loads(
                self.env["ir.config_parameter"].sudo().get_param("mgs.version_history") or "[]")
        except ValueError:
            history = []
        return {
            "codigo": code_version,
            "aplicado": module.latest_version or None,
            "estado": module.state or None,
            "coincide": _module_tail(module.latest_version) == _module_tail(code_version),
            "historico_versiones": history,
        }

    def _section_engine(self):
        odoo_dir = _RUNTIME_ROOT / "odoo"
        try:
            pinned = (_RUNTIME_ROOT / "odoo-revision.txt").read_text(encoding="utf-8").strip()
        except OSError:
            pinned = None
        head = _git(odoo_dir, "rev-parse", "HEAD")
        diff = _git(odoo_dir, "diff", "--quiet", "HEAD")
        head_sha = head.stdout.strip() if head and head.returncode == 0 else None
        return {
            "revision_fijada": pinned,
            "revision_actual": head_sha,
            "coincide": bool(head_sha and pinned and head_sha == pinned),
            "sin_modificaciones_locales": (diff.returncode == 0) if diff else None,
        }

    def _section_common_config(self):
        env = self.env
        company = env.company
        icp = env["ir.config_parameter"].sudo()
        owner = env["res.users"].sudo()._mgs_owner()
        access = env["mgs.access"].sudo()._get()
        shop = env.ref("mi_gestor_stock.pos_config_shop", raise_if_not_found=False)
        roots_hidden = all(
            not menu.active
            for menu in (env.ref(x, raise_if_not_found=False) for x in _NATIVE_ROOT_MENUS)
            if menu)
        timezones = sorted(set(
            env["res.users"].sudo().search([("active", "=", True)]).mapped("tz")))
        return {
            "idiomas_activos": [code for code, _name in env["res.lang"].get_installed()],
            "moneda": company.currency_id.name,
            "pais": company.country_id.code,
            "plan_contable": company.chart_template or None,
            "zonas_horarias_de_usuarios": timezones,
            "caja_tienda": {
                "existe": bool(shop),
                "plano_de_mesas": bool(shop and shop.module_pos_restaurant),
                "tarifas_activas": bool(shop and shop.use_pricelist),
                "control_de_precio_restringido": bool(shop and shop.restrict_price_control),
            },
            "menus_raiz_nativos_ocultos": roots_hidden,
            "registro_publico_invitados": icp.get_param("auth_signup.allow_uninvited"),
            "reset_por_correo": icp.get_param("auth_signup.reset_password"),
            "propietaria_configurada": bool(owner and owner.mgs_password_set),
            "clave_recuperacion_creada": bool(access.recovery_generated_at),
            "primer_acceso": access.activation_state,
        }

    def _section_modules(self):
        return [
            {"nombre": m.name, "version": m.latest_version}
            for m in self.env["ir.module.module"].sudo().search(
                [("state", "=", "installed")], order="name")
        ]

    @api.model
    def _gather_text(self):
        return json.dumps(self._gather(), indent=2, ensure_ascii=False, sort_keys=True)

    @api.model
    def action_open(self):
        from .mgs_permissions import require_manager
        require_manager(self.env)
        rec = self.create({"report_text": self._gather_text()})
        return {
            "type": "ir.actions.act_window",
            "name": _("Diagnóstico de instalación"),
            "res_model": "mgs.diagnostic",
            "res_id": rec.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_download(self):
        self.ensure_one()
        from .mgs_permissions import require_manager
        require_manager(self.env)
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        attachment = self.env["ir.attachment"].create({
            "name": "diagnostico-%s-%s.json" % (self.env.cr.dbname, stamp),
            "type": "binary",
            "raw": (self.report_text or self._gather_text()).encode("utf-8"),
            "mimetype": "application/json",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
