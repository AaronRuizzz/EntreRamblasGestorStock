# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

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

    # ------------------------------------------------------------------
    # Recepción y caducidad (se actualizan en cada entrada de mercancía,
    # ver models/mgs_reception.py -> action_confirm)
    # ------------------------------------------------------------------
    mgs_reception_date = fields.Date(
        "Última recepción", readonly=True,
        help="Fecha de la última entrada de mercancía de este producto.")
    mgs_expiry_date = fields.Date(
        "Caduca el",
        help="Caducidad de la última tanda recibida. Se actualiza en cada recepción.")
    mgs_expired = fields.Boolean("Caducado", compute="_compute_mgs_expired")

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

    @api.depends("mgs_expiry_date")
    def _compute_mgs_expired(self):
        today = fields.Date.context_today(self)
        for tmpl in self:
            tmpl.mgs_expired = bool(tmpl.mgs_expiry_date and tmpl.mgs_expiry_date < today)

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
    # Resumen para la página de inicio (static/src/js/home.js)
    # ------------------------------------------------------------------
    @api.model
    def mgs_home_summary(self):
        low = len(self._mgs_low_stock_ids())
        pending = self.env["mgs.stock.alert.notice"].search_count([("is_read", "=", False)])
        return {
            "alerts": low + pending,
            "products": self.search_count([("is_storable", "=", True)]),
        }

    # ------------------------------------------------------------------
    # Datos del panel de Stock (lo consume static/src/js/stock_dashboard.js)
    # ------------------------------------------------------------------
    @api.model
    def mgs_dashboard_data(self):
        products = self.search([("is_storable", "=", True)])

        # --- 1. Avisos ---
        alerts = []
        threshold_alerts = self.env["mgs.stock.alert"].search([("alert_type", "=", "threshold")])
        for alert in threshold_alerts:
            if not alert._mgs_is_below_threshold():
                continue
            alerts.append({
                "kind": "threshold",
                "notice_id": False,          # los de cantidad no se descartan a mano
                "product_id": alert.product_id.id,
                "message": _("%(prod)s: quedan %(qty).0f uds. (aviso a %(min).0f)",
                             prod=alert.product_id.name,
                             qty=alert.product_id.qty_available,
                             min=alert.min_qty),
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
        for tmpl in products.filtered(lambda p: p.mgs_expiry_date):
            days = (tmpl.mgs_expiry_date - today).days
            if days <= 3:
                expiring.append({
                    "product_id": tmpl.id,
                    "name": tmpl.name,
                    "expiry": fields.Date.to_string(tmpl.mgs_expiry_date),
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
        }
