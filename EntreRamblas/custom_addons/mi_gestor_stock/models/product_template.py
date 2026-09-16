# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from .mgs_permissions import require_operator, is_manager

# Cuantas tarjetas de "stock mas bajo" muestra el panel de Stock.
LOW_STOCK_CARDS = 3


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # En una floristería física, todos los productos creados deben ser por defecto:
    # 1. Almacenables (con control de stock real en tienda)
    # 2. Disponibles para venta
    # 3. Disponibles en el TPV (Punto de Venta)
    is_storable = fields.Boolean(default=True)
    sale_ok = fields.Boolean(default=True)
    available_in_pos = fields.Boolean(default=True)
    mgs_auto_lots = fields.Boolean("Partidas automáticas", default=False,
                                   help="El TPV asigna las partidas por caducidad y antigüedad.")

    # ------------------------------------------------------------------
    # Recepción y caducidad (se actualizan en cada entrada de mercancía,
    # ver models/mgs_reception.py -> action_confirm)
    # ------------------------------------------------------------------
    mgs_reception_date = fields.Date(
        "Última recepción", readonly=True,
        help="Fecha de la última entrada de mercancía de este producto.")
    mgs_expiry_date = fields.Date(
        "Próxima caducidad", compute="_compute_mgs_next_expiry",
        help="Primera caducidad de las partidas con existencias. Se conserva cada recepción por separado.")
    mgs_expired = fields.Boolean("Caducado", compute="_compute_mgs_expired", search="_search_mgs_expired")

    # ------------------------------------------------------------------
    # Avisos de stock (modelo mgs.stock.alert)
    # ------------------------------------------------------------------
    mgs_alert_ids = fields.One2many("mgs.stock.alert", "product_id", string="Avisos")
    mgs_alert_count = fields.Integer(compute="_compute_mgs_alert_count")
    mgs_low_stock = fields.Boolean(
        string="Bajo mínimo",
        compute='_compute_mgs_low_stock',
        search='_search_mgs_low_stock',
        help="El producto tiene un aviso por cantidad y está en el límite o por debajo.")

    # ------------------------------------------------------------------
    # Categoría: una sola, la del almacén, que vale también para la caja
    # (el porqué y el espejo, en models/product_category.py)
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._mgs_apply_pos_category()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if "categ_id" in vals:
            self._mgs_apply_pos_category()
        return res

    def _mgs_apply_pos_category(self):
        """`pos_categ_ids` (el botón del TPV) sigue a `categ_id` (la categoría
        del almacén).

        La ficha del producto no enseña la pestaña «Punto de venta»
        (views/product_views.xml): la categoría se elige UNA vez, al recibir el
        producto, y la caja se entera sola. Un producto cuya categoría no tiene
        botón —las de fábrica, archivadas— se queda sin él: en el TPV sigue
        saliendo en la parrilla general y en el buscador.
        """
        for tmpl in self:
            mirror = tmpl.categ_id.sudo().mgs_pos_categ_id
            if tmpl.pos_categ_ids != mirror:
                tmpl.pos_categ_ids = [(6, 0, mirror.ids)]

    def _mgs_available_lot_quants(self):
        return self.env["stock.quant"].search([
            ("product_id.product_tmpl_id", "in", self.ids),
            ("company_id", "=", self.env.company.id),
            ("location_id.usage", "=", "internal"),
            ("quantity", ">", 0), ("lot_id", "!=", False),
        ])

    @api.depends("qty_available")
    def _compute_mgs_next_expiry(self):
        dates = {}
        for quant in self._mgs_available_lot_quants():
            if quant.lot_id.expiration_date:
                key = quant.product_id.product_tmpl_id.id
                date = fields.Datetime.context_timestamp(self, quant.lot_id.expiration_date).date()
                dates[key] = min(dates.get(key, date), date)
        for product in self:
            product.mgs_expiry_date = dates.get(product.id, False)

    @api.depends("mgs_expiry_date")
    def _compute_mgs_expired(self):
        today = fields.Date.context_today(self)
        for tmpl in self:
            tmpl.mgs_expired = bool(tmpl.mgs_expiry_date and tmpl.mgs_expiry_date < today)

    def _search_mgs_expired(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("Operador no soportado para caducidad."))
        expired = self.search([]).filtered("mgs_expired")
        return [("id", "in" if (operator == "=") == bool(value) else "not in", expired.ids)]

    @api.depends("mgs_alert_ids")
    def _compute_mgs_alert_count(self):
        for tmpl in self:
            tmpl.mgs_alert_count = len(tmpl.mgs_alert_ids)

    @api.depends('qty_available', 'mgs_alert_ids.min_qty', 'mgs_alert_ids.alert_type')
    def _compute_mgs_low_stock(self):
        for tmpl in self:
            tmpl.mgs_low_stock = any(
                alert._mgs_is_below_threshold() for alert in tmpl.mgs_alert_ids)

    def _search_mgs_low_stock(self, operator, value):
        """`qty_available` es computado no almacenado y su propio `search`
        (`stock._search_qty_available`) exige un literal numerico como operando
        derecho: un dominio tipo [('qty_available','<=','min_qty')] lanza UserError.
        La forma correcta es este booleano no almacenado con `search=`, resuelto
        en Python (mismo patron que usa `stock` para qty_available)."""
        if operator not in ('=', '!='):
            raise UserError(_("Operador no soportado para «Bajo mínimo»: %s", operator))
        positive = (operator == '=') == bool(value)
        ids = self._mgs_low_stock_ids()
        return [('id', 'in' if positive else 'not in', ids)]

    @api.model
    def _mgs_low_stock_ids(self):
        """Ids de los productos con algun aviso por cantidad saltando ahora mismo."""
        alerts = self.env["mgs.stock.alert"].sudo().search([("alert_type", "=", "threshold")])
        return [a.product_id.id for a in alerts if a._mgs_is_below_threshold()]

    def action_mgs_open_alerts(self):
        """Smart button de la ficha de producto."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Avisos de %s", self.name),
            "res_model": "mgs.stock.alert",
            "view_mode": "list,form",
            "domain": [("product_id", "=", self.id)],
            "context": {"default_product_id": self.id},
        }

    # ------------------------------------------------------------------
    # Código de barras y etiquetas (impresora térmica, ver mgs_config.py)
    # ------------------------------------------------------------------
    def action_mgs_generate_barcode(self):
        """Asigna un código interno a un producto que llegó sin código.

        Pasa mucho en floristería: flores a granel, envoltorios o composiciones
        propias no traen EAN del proveedor. Con un código interno impreso en
        una etiqueta, el producto ya se puede escanear en caja igual que
        cualquier otro.
        """
        config = self.env["mgs.config"]
        for tmpl in self:
            if not tmpl.barcode:
                tmpl.barcode = config.mgs_next_internal_barcode()
        return True

    def action_mgs_print_label(self):
        """Imprime la etiqueta del producto en la térmica de 80 mm."""
        require_operator(self.env)
        self.check_access("read")
        config = self.env["mgs.config"]._mgs_get()
        return config._mgs_print_labels(self)

    @api.model
    def mgs_find_by_barcode(self, barcode):
        """Busca un producto por código escaneado (lo usa el panel de Stock).

        Se mira también la referencia interna: en la tienda conviven códigos
        de proveedor y etiquetas propias.
        """
        code = self.env["mgs.config"].mgs_clean_scan(barcode)
        if not code:
            return False
        tmpl = self.search([("barcode", "=", code)], limit=1)
        if not tmpl:
            tmpl = self.search([("default_code", "=", code)], limit=1)
        if not tmpl:
            return False
        return {"id": tmpl.id, "name": tmpl.display_name}

    # ------------------------------------------------------------------
    # Resumen para la página de inicio (static/src/js/home.js)
    # ------------------------------------------------------------------
    @api.model
    def mgs_home_summary(self):
        require_operator(self.env)
        low = len(self._mgs_low_stock_ids())
        pending = self.env["mgs.stock.alert.notice"].search_count([("is_read", "=", False)])
        manager = is_manager(self.env)
        return {
            "alerts": low + pending,
            "is_manager": manager,
            "backup_warning": self.env["mgs.backup"]._mgs_status_warning() if manager else False,
            "update_notice": self.env["mgs.update"]._summary()["label"] if manager else "",
            "products": self.search_count([("is_storable", "=", True)]),
        }

    # ------------------------------------------------------------------
    # Datos del panel de Stock (lo consume static/src/js/stock_dashboard.js)
    # ------------------------------------------------------------------
    @api.model
    def mgs_dashboard_data(self):
        require_operator(self.env)
        products = self.search([("is_storable", "=", True)])

        # --- 1. Avisos ---
        alerts = []
        threshold_alerts = self.env["mgs.stock.alert"].search([("alert_type", "=", "threshold")])
        for alert in threshold_alerts:
            if not alert._mgs_is_below_threshold():
                continue
            message = _("%(prod)s: quedan %(qty).0f uds. (aviso a %(min).0f)",
                        prod=alert.product_id.name,
                        qty=alert.product_id.qty_available,
                        min=alert.min_qty)
            if alert.name:
                message = "%s · %s" % (alert.name, message)
            alerts.append({
                "kind": "threshold",
                "notice_id": False,          # los de cantidad no se descartan a mano
                "product_id": alert.product_id.id,
                "message": message,
            })
        notices = self.env["mgs.stock.alert.notice"].search([("is_read", "=", False)])
        for notice in notices:
            alerts.append({
                "kind": "periodic",
                "notice_id": notice.id,
                "product_id": notice.product_id.id,
                "message": notice.name,
            })

        # --- 2. Caducados / por caducar ---
        today = fields.Date.context_today(self)
        expiring = []
        lots = products._mgs_available_lot_quants().lot_id
        for lot in lots.filtered("expiration_date"):
            expiry = fields.Datetime.context_timestamp(self, lot.expiration_date).date()
            days = (expiry - today).days
            if days <= 3:
                expiring.append({
                    "product_id": lot.product_id.product_tmpl_id.id,
                    "name": "%s · %s" % (lot.product_id.name, lot.name),
                    "lot_id": lot.id,
                    "expiry": fields.Date.to_string(expiry),
                    "days": days,
                })
        expiring.sort(key=lambda e: e["days"])

        # --- 3. Los N productos con menos stock ---
        # qty_available es computado no almacenado -> hay que ordenar en Python.
        ordered = products.sorted(key=lambda p: p.qty_available)
        low_stock = [{
            "id": p.id,
            "name": p.name,
            "qty": p.qty_available,
            "uom": p.uom_id.name,
            "categ": p.categ_id.name,
        } for p in ordered[:LOW_STOCK_CARDS]]

        # --- 4. Productos agrupados por categoría ---
        categories = {}
        for tmpl in products.sorted(key=lambda p: (p.categ_id.name or "", p.name or "")):
            categ = categories.setdefault(tmpl.categ_id.id, {
                "id": tmpl.categ_id.id,
                "name": tmpl.categ_id.name or _("Sin categoría"),
                "products": [],
            })
            categ["products"].append({
                "id": tmpl.id,
                "name": tmpl.name,
                "barcode": tmpl.barcode,
                "qty": tmpl.qty_available,
                "uom": tmpl.uom_id.name,
                "price": tmpl.list_price,
                "expiry": fields.Date.to_string(tmpl.mgs_expiry_date) if tmpl.mgs_expiry_date else False,
                "expired": tmpl.mgs_expired,
                "low": tmpl.mgs_low_stock,
            })

        return {
            "alerts": alerts,
            "expiring": expiring,
            "low_stock": low_stock,
            "categories": list(categories.values()),
            "currency": self.env.company.currency_id.symbol,
            # Recepción y la configuración de avisos son solo de la responsable:
            # el panel esconde esos accesos para la dependienta (que aquí solo
            # consulta), igual que hace la página de inicio.
            "is_manager": is_manager(self.env),
        }
