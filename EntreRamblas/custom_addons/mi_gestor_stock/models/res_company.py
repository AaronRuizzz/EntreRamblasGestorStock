import base64
import logging

from odoo import models
from odoo.tools import file_path

_logger = logging.getLogger(__name__)

COMPANY_NAME = "Entre Ramblas · Clavel & Azahar"
LANG_CODE = "es_ES"
TZ_CODE = "Europe/Madrid"
_IMG_DIR = "mi_gestor_stock/static/src/img"

# El acceso inicial se provisiona fuera del módulo; nunca fijar contraseñas en código.


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

        # NOMBRE COMERCIAL vs. RAZÓN SOCIAL FISCAL. `res.company.name` es el
        # nombre legal: sale en el ticket y en las facturas, y una vez que la
        # dueña pone el de verdad, una actualización NO lo sobrescribe. El
        # nombre comercial (emblema, inicio, título de pestaña) vive aparte,
        # en el parámetro `mgs.commercial_name`, con este valor de partida.
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param("mgs.commercial_name"):
            icp.set_param("mgs.commercial_name", COMPANY_NAME)

        vals = {}
        if not company.name or company.name in ("My Company", "YourCompany", COMPANY_NAME):
            vals["name"] = COMPANY_NAME
        # Emblema definitivo (mismo que el login) con respaldo al antiguo.
        logo = _img_b64("logo-emblema.png") or _img_b64("logo.png")
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

        # Moneda en euros (Odoo instala la empresa en USD por defecto).
        eur = self.env.ref("base.EUR", raise_if_not_found=False)
        if eur and company.currency_id != eur:
            if not eur.active:
                eur.active = True
            try:
                company.currency_id = eur
            except Exception:  # noqa: BLE001 - con asientos contables no se puede
                _logger.warning("mi_gestor_stock: no se pudo cambiar la moneda a EUR")

        # Pais: Espana (Odoo instala la empresa con pais vacio o US).
        # Necesario para: direccion en facturas/albaranes, formato NIF/CIF
        # y reglas de posicion fiscal de l10n_es.
        spain = self.env.ref("base.es", raise_if_not_found=False)
        if spain and company.country_id != spain:
            company.country_id = spain

        self._mgs_rename_picking_types()
        self._mgs_stamp_version()

        _logger.info("mi_gestor_stock: marca aplicada -> %s", COMPANY_NAME)

    # ------------------------------------------------------------------
    # Manifiesto de versión: histórico de qué versión del módulo se ha
    # aplicado a esta base y cuándo. Se anota en cada `-u` (que es cuando
    # corren también las migraciones). Lo lee el diagnóstico.
    # ------------------------------------------------------------------
    def _mgs_stamp_version(self):
        import json
        from datetime import datetime, timezone
        from odoo.modules.module import get_manifest
        version = get_manifest("mi_gestor_stock").get("version")
        icp = self.env["ir.config_parameter"].sudo()
        try:
            history = json.loads(icp.get_param("mgs.version_history") or "[]")
        except ValueError:
            history = []
        if not history or history[-1].get("version") != version:
            history.append({
                "version": version,
                "aplicada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            icp.set_param("mgs.version_history", json.dumps(history[-50:]))

    # ------------------------------------------------------------------
    # Nombres de los tipos de operacion que salen en la pantalla de inicio
    # ------------------------------------------------------------------
    def _mgs_rename_picking_types(self):
        """El TPV crea su tipo de operacion como 'PoS Orders' y el almacen por defecto
        viene como 'My Company', en ingles y sin traduccion."""
        renames = {
            "PoS Orders": "Pedidos TPV",
            "PoS Orders Refund": "Devoluciones TPV",
        }
        picking_types = self.env["stock.picking.type"].with_context(
            active_test=False
        ).search([("name", "in", list(renames))])
        for picking_type in picking_types:
            picking_type.name = renames[picking_type.name]

        # Renombrar almacenes que sigan con el nombre por defecto 'My Company'
        warehouses = self.env["stock.warehouse"].with_context(active_test=False).search([("name", "=", "My Company")])
        for wh in warehouses:
            wh.name = COMPANY_NAME

    # ------------------------------------------------------------------
    # Tarifas de campana: activa el uso de tarifas en las cajas ya
    # configuradas, sin exigir ninguna concreta. Si no hay ninguna caja
    # todavia (instalacion nueva), no hace nada; se aplica solo al volver a
    # ejecutar esto en el siguiente `-u`, ya con la caja creada.
    # ------------------------------------------------------------------
    def _mgs_apply_pos_pricelist_defaults(self):
        configs = self.env["pos.config"].search([])
        if configs:
            configs.write({"use_pricelist": True, "restrict_price_control": True})

    # ------------------------------------------------------------------
    # Caja de la tienda: el boton «Vender» entra directo a /pos/ui, asi que
    # tiene que haber SIEMPRE una caja lista. Con --without-demo Odoo no crea
    # ninguna, y el asistente «que vendes» del TPV puede crear una de tipo
    # restaurante (plano de mesas) por error. Aqui se garantiza una sola caja
    # de tienda, sin nada de restaurante. Idempotente: en un -u posterior solo
    # comprueba y no crea nada.
    # ------------------------------------------------------------------
    def _mgs_ensure_shop_pos_config(self):
        Config = self.env["pos.config"].sudo()
        existing = Config.search([])
        # Nunca plano de mesas: ni en la nuestra ni en una que ya exista.
        # Odoo protege esa opción mientras una sesión está abierta; forzarla
        # entonces abortaría todo el ``-u`` y podría interrumpir una venta. En
        # ese caso se conserva la caja temporalmente y se corrige en la próxima
        # actualización, una vez cerrada la sesión.
        restaurant = existing.filtered("module_pos_restaurant")
        open_restaurant = restaurant.filtered(
            lambda config: config.session_ids.filtered(lambda session: session.state != "closed"))
        closable_restaurant = restaurant - open_restaurant
        if closable_restaurant:
            closable_restaurant.write({"module_pos_restaurant": False})
        if open_restaurant:
            _logger.warning(
                "mi_gestor_stock: se aplaza quitar el plano de mesas de la caja %s "
                "porque tiene una sesión abierta; ciérrala y vuelve a actualizar el módulo",
                ", ".join(open_restaurant.mapped("name")),
            )

        shop = self.env.ref("mi_gestor_stock.pos_config_shop", raise_if_not_found=False)
        if not shop:
            shop = existing.filtered(lambda c: not c.module_pos_restaurant)[:1]
        if not shop and open_restaurant:
            # No crear otra caja mientras la única existente está en uso. Se
            # conserva como la caja de tienda y el cambio de modo queda
            # aplazado por la guarda anterior.
            shop = open_restaurant[:1]
        if not shop:
            try:
                journal, payment_method_ids = Config._create_journal_and_payment_methods()
            except Exception:  # noqa: BLE001 - sin plan contable no se puede; no romper el -u
                _logger.exception("mi_gestor_stock: no se pudo preparar la caja de la tienda")
                return
            shop = Config.create({
                "name": "Tienda",
                "company_id": self.env.company.id,
                "journal_id": journal.id,
                "payment_method_ids": [(6, 0, payment_method_ids)],
            })
        # El asistente inicial de Odoo usa estos nombres para su caja de
        # demostración. Una vez reutilizada como caja normal, no dejar un
        # rótulo que haga pensar que el modo restaurante sigue activo. Los
        # nombres elegidos por el usuario se respetan.
        if shop.name in ("Restaurant", "Restaurante"):
            shop.name = "Tienda"
        self.env["ir.model.data"]._update_xmlids([{
            "xml_id": "mi_gestor_stock.pos_config_shop",
            "record": shop,
            "noupdate": True,
        }])

    # ------------------------------------------------------------------
    # Numeracion de eventos y encargos: EVENTO/%(year)s/, no BODA/%(year)s/.
    # El <record> de data/mgs_event_data.xml vive en un bloque noupdate="1"
    # (asi no se pierde la numeracion ya emitida en cada -u), asi que
    # cambiar el prefijo ahi NO hace nada sobre una base ya instalada: hace
    # falta escribirlo aqui, igual que _mgs_apply_branding hace con
    # base.main_company por el mismo motivo. Solo se tocan `prefix` y
    # `name`: nunca `number_next`, para no reiniciar el contador ni
    # renumerar lo que ya se emitio con el prefijo antiguo.
    # ------------------------------------------------------------------
    def _mgs_apply_event_sequence(self):
        seq = self.env.ref("mi_gestor_stock.seq_mgs_event", raise_if_not_found=False)
        if seq and seq.prefix != "EVENTO/%(year)s/":
            seq.write({"prefix": "EVENTO/%(year)s/", "name": "Eventos y encargos"})

    # ------------------------------------------------------------------
    # Plan contable espanol: una instalacion realmente nueva se queda con el
    # plan GENERICO aunque l10n_es sea dependencia (Odoo solo lo autoinstala
    # al CREAR la compania con pais ya puesto; aqui el pais se fija despues,
    # por escritura, en _mgs_apply_branding). Sin el plan espanol no existen
    # los IVA 0/4/10/21 que ALLOWED_VAT (mgs_catalog_import.py) da por
    # hechos, y el alta de catalogo falla.
    #
    # Dos guardas, y son lo importante: esto se ejecuta en cada `-u`, TAMBIEN
    # sobre una base con contabilidad real.
    #   1. Si la compania YA tiene un plan espanol (chart_template empieza
    #      por "es"), no se toca nada.
    #   2. Si existe algun asiento contable de verdad (_existing_accounting,
    #      el mismo metodo que usa el propio Odoo antes de recargar un plan
    #      en Ajustes > Contabilidad), tampoco se toca nada: cargar un plan
    #      encima de asientos existentes seria destructivo. Se avisa en el
    #      log para que se cargue a mano y se sale sin lanzar.
    # Todo dentro de un try/except: un fallo aqui nunca debe impedir instalar.
    # ------------------------------------------------------------------
    def _mgs_ensure_spanish_chart(self):
        company = self.env.ref("base.main_company", raise_if_not_found=False)
        if not company:
            company = self.env["res.company"].search([], order="id", limit=1)
        if not company:
            return
        if company.chart_template and company.chart_template.startswith("es"):
            return
        if company.sudo()._existing_accounting():
            _logger.warning(
                "mi_gestor_stock: %s ya tiene asientos contables con un plan "
                "no espanol (%s); carga el plan contable espanol a mano desde "
                "Contabilidad > Configuracion si hace falta.",
                company.name, company.chart_template or "genérico",
            )
            return
        try:
            self.env["account.chart.template"].try_loading("es_pymes", company, install_demo=False)
            _logger.info("mi_gestor_stock: plan contable espanol (es_pymes) cargado para %s", company.name)
        except Exception:  # noqa: BLE001 - un fallo aqui no debe impedir instalar
            _logger.exception("mi_gestor_stock: fallo al cargar el plan contable espanol")

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

        # Idioma por defecto para usuarios nuevos y existentes. Esto va
        # ANTES de desactivar en_US: Odoo no deja desactivar un idioma que
        # todavia usa algun usuario ("Cannot deactivate a language that is
        # currently used by users").
        self.env["ir.default"].set("res.partner", "lang", LANG_CODE)
        # Zona horaria tambien: sin "Ajustes" (donde vivia Preferencias) ya
        # no hay pantalla para corregirla a mano, y con tz vacio las horas
        # se pintan en UTC en vez de en la hora real de la tienda.
        self.env["res.users"].with_context(active_test=False).search([]).write(
            {"lang": LANG_CODE, "tz": TZ_CODE}
        )
        self.env["res.partner"].with_context(active_test=False).search(
            [("lang", "!=", LANG_CODE)]
        ).write({"lang": LANG_CODE})

        # Nombre visible del administrador; no modificar credenciales existentes.
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        if admin:
            if admin.name in ("Administrator", "Mitchell Admin"):
                admin.name = "Administrador"


        # Ahora si: deja el espanol como UNICO idioma activo, para que la
        # pantalla de login y cualquier pagina anonima salgan en espanol.
        # (en_US sigue siendo el idioma fuente interno de Odoo aunque este
        # inactivo; para reactivarlo: Ajustes > Traducciones > Idiomas.)
        en = lang_model.with_context(active_test=False).search(
            [("code", "=", "en_US")], limit=1
        )
        if en and en.active:
            try:
                en.active = False
            except Exception:  # noqa: BLE001 - no bloquear el update
                _logger.warning("mi_gestor_stock: no se pudo desactivar en_US todavia")

        _logger.info("mi_gestor_stock: interfaz configurada en %s", LANG_CODE)
