import base64
import logging

from odoo import models
from odoo.tools import file_path

_logger = logging.getLogger(__name__)

COMPANY_NAME = "Entre Ramblas · Clavel & Azahar"
LANG_CODE = "es_ES"
_IMG_DIR = "mi_gestor_stock/static/src/img"


def _img_b64(filename):
    """Lee un PNG del modulo y lo devuelve en base64 (o None si no existe)."""
    try:
        path = file_path(f"{_IMG_DIR}/{filename}", filter_ext=(".png",))
    except (FileNotFoundError, ValueError):
        return None
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read())


class ResCompany(models.Model):
    _inherit = "res.company"

    # ------------------------------------------------------------------
    # Marca: nombre + logo + favicon de la empresa
    # ------------------------------------------------------------------
    def _mgs_apply_branding(self):
        company = self.env.ref("base.main_company", raise_if_not_found=False)
        if not company:
            company = self.env["res.company"].search([], order="id", limit=1)
        if not company:
            return

        vals = {"name": COMPANY_NAME}
        logo = _img_b64("logo.png")
        if logo:
            vals["logo"] = logo
        # `res.company.favicon` no existe en Odoo 18 Community sin el modulo
        # `website`; el favicon del login se fija en la plantilla (x_icon).
        if "favicon" in self._fields:
            favicon = _img_b64("favicon.png")
            if favicon:
                vals["favicon"] = favicon
        company.write(vals)

        # El partner de la empresa hereda el nombre; renombra tambien
        # cualquier resto de la instalacion por defecto ("My Company").
        stale = self.env["res.partner"].search([("name", "=", "My Company")])
        if stale:
            stale.write({"name": COMPANY_NAME})

        _logger.info("mi_gestor_stock: marca aplicada -> %s", COMPANY_NAME)

    # ------------------------------------------------------------------
    # Idioma: espanol (es_ES) para toda la interfaz
    # ------------------------------------------------------------------
    def _mgs_setup_spanish(self):
        lang_model = self.env["res.lang"]
        existing = lang_model.with_context(active_test=False).search(
            [("code", "=", LANG_CODE)], limit=1
        )
        # Estado ANTES de activar: si aun no estaba activo, hay que
        # importar las traducciones (.po) de los modulos instalados.
        needs_translations = not (existing and existing.active)

        lang_model._activate_lang(LANG_CODE)
        lang_rec = lang_model.with_context(active_test=False).search(
            [("code", "=", LANG_CODE)], limit=1
        )
        if not lang_rec:
            return
        lang_rec.active = True

        if needs_translations:
            # Es lento (~1 min). Para forzar una recarga despues:
            # Ajustes > Traducciones > Cargar una traduccion.
            try:
                self.env["base.language.install"].create(
                    {"lang_ids": [(6, 0, lang_rec.ids)], "overwrite": True}
                ).lang_install()
            except Exception:  # noqa: BLE001 - no bloquear el update
                _logger.exception("mi_gestor_stock: fallo al cargar traducciones es_ES")

        # Deja el espanol como UNICO idioma activo: asi la pantalla de
        # login y cualquier pagina anonima tambien salen en espanol.
        # (en_US sigue siendo el idioma fuente interno de Odoo aunque
        # este inactivo; para reactivarlo: Ajustes > Traducciones > Idiomas.)
        en = lang_model.with_context(active_test=False).search(
            [("code", "=", "en_US")], limit=1
        )
        if en and en.active:
            en.active = False

        # Idioma por defecto para usuarios nuevos y existentes.
        self.env["ir.default"].set("res.partner", "lang", LANG_CODE)
        self.env["res.users"].with_context(active_test=False).search([]).write(
            {"lang": LANG_CODE}
        )
        self.env["res.partner"].with_context(active_test=False).search(
            [("lang", "!=", LANG_CODE)]
        ).write({"lang": LANG_CODE})

        # Nombre del usuario administrador en espanol.
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        if admin and admin.name in ("Administrator", "Mitchell Admin"):
            admin.name = "Administrador"

        _logger.info("mi_gestor_stock: interfaz configurada en %s", LANG_CODE)
