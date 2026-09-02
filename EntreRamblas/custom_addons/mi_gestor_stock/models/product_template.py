# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


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
    # Alertas de stock mínimo
    # ------------------------------------------------------------------
    mgs_alert_on = fields.Boolean(
        string="Avisar si baja del mínimo", default=False)
    mgs_min_qty = fields.Float(
        string="Stock mínimo", digits='Product Unit of Measure', default=0.0,
        help="Cuando las existencias bajen de esta cantidad, el producto "
             "aparecerá en Stock > Alertas y se avisará cada día.")
    mgs_low_stock = fields.Boolean(
        string="Bajo mínimo",
        compute='_compute_mgs_low_stock',
        search='_search_mgs_low_stock')

    @api.depends('qty_available', 'mgs_min_qty', 'mgs_alert_on', 'is_storable')
    def _compute_mgs_low_stock(self):
        for tmpl in self:
            tmpl.mgs_low_stock = bool(
                tmpl.is_storable and tmpl.mgs_alert_on
                and float_compare(
                    tmpl.qty_available, tmpl.mgs_min_qty,
                    precision_rounding=tmpl.uom_id.rounding or 0.01) < 0
            )

    def _search_mgs_low_stock(self, operator, value):
        """`qty_available` es computado no almacenado y su propio `search`
        (`stock._search_qty_available`) exige un literal numerico como
        operando derecho: un dominio tipo [('qty_available','<=','mgs_min_qty')]
        lanza UserError. La forma correcta es este booleano no almacenado con
        `search=`, resuelto en Python (mismo patron que usa `stock` para
        qty_available/virtual_available)."""
        if operator not in ('=', '!='):
            raise UserError(_("Operador no soportado para «Bajo mínimo»: %s", operator))
        positive = (operator == '=') == bool(value)
        ids = self._mgs_low_stock_ids()
        return [('id', 'in' if positive else 'not in', ids)]

    @api.model
    def _mgs_low_stock_ids(self):
        """Candidatos por dominio ALMACENADO (sin recursion) y filtro en Python."""
        candidates = self.sudo().search([
            ('is_storable', '=', True),
            ('mgs_alert_on', '=', True),
        ])
        return candidates.filtered(lambda t: float_compare(
            t.qty_available, t.mgs_min_qty,
            precision_rounding=t.uom_id.rounding or 0.01) < 0).ids

    # ------------------------------------------------------------------
    # Aviso diario (ir.cron, ver data/cron_alerts.xml)
    # ------------------------------------------------------------------
    @api.model
    def _mgs_cron_stock_alerts(self):
        """Deja una actividad de aviso en cada producto bajo minimo y cierra
        las de los que ya se repusieron. Idempotente: no duplica el aviso si
        ya hay uno abierto del mismo tipo."""
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return
        admin = self.env.ref('base.user_admin', raise_if_not_found=False) or self.env.user

        low = self.browse(self._mgs_low_stock_ids())
        for tmpl in low:
            has_open_activity = tmpl.activity_ids.filtered(
                lambda a: a.activity_type_id == activity_type)
            if has_open_activity:
                continue
            tmpl.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=admin.id,
                summary=_("Stock bajo mínimo"),
                note=_("Quedan %(qty)s uds. (mínimo %(min)s).",
                       qty=tmpl.qty_available, min=tmpl.mgs_min_qty),
            )

        # Cierra los avisos de los productos que ya no estan bajo minimo.
        stale = self.search([('mgs_alert_on', '=', True), ('id', 'not in', low.ids)])
        stale_activities = stale.activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type)
        stale_activities.unlink()
