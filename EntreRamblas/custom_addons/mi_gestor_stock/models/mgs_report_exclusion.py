# -*- coding: utf-8 -*-
"""Clasificación global de líneas que no deben aparecer en informes.

La operación del TPV no se toca: solo se cambia la presentación de informes.
Las devoluciones heredan el estado de la línea que rectifican para que nunca
aparezca una devolución aislada de una venta que se ha excluido.
"""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .mgs_permissions import require_manager


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    mgs_in_b = fields.Boolean("Excluir de informes", copy=False, index=True)
    mgs_report_excluded = fields.Boolean(
        "Excluida de informes", compute="_compute_mgs_report_excluded",
        store=True, index=True, copy=False,
        help="Las devoluciones toman automáticamente el estado de la línea vendida.")

    @api.depends("mgs_in_b", "refunded_orderline_id.mgs_in_b")
    def _compute_mgs_report_excluded(self):
        for line in self:
            line.mgs_report_excluded = (
                line.refunded_orderline_id.mgs_in_b
                if line.refunded_orderline_id else line.mgs_in_b)

    def action_mgs_set_report_exclusion(self, excluded, reason):
        """Único punto de escritura de la clasificación, con historial."""
        require_manager(self.env)
        lines = self.filtered(lambda line: line.qty > 0 and not line.refunded_orderline_id)
        if len(lines) != len(self):
            raise UserError(_("Solo se pueden clasificar líneas de venta originales."))
        reason = (reason or "").strip()
        if not reason:
            raise UserError(_("Indica el motivo del cambio."))
        for line in lines:
            previous = line.mgs_in_b
            if previous == bool(excluded):
                continue
            super(PosOrderLine, line).write({"mgs_in_b": bool(excluded)})
            self.env["mgs.report.exclusion.log"].sudo().with_context(
                mgs_report_exclusion_change=True).create({
                "line_id": line.id, "was_excluded": previous,
                "is_excluded": bool(excluded), "reason": reason,
                "user_id": self.env.user.id,
            })
        # Las vistas previas son instantáneas: se vuelven a calcular antes de exportar.
        self.env["mgs.report.template"].search([])._mgs_write_server_fields(
            {"preview_stale": True})
        return True

    def write(self, vals):
        if "mgs_in_b" in vals and not self.env.context.get("mgs_report_exclusion_change"):
            raise AccessError(_("La clasificación se cambia desde Preparar ventas, indicando un motivo."))
        return super().write(vals)


class MgsReportExclusionLog(models.Model):
    _name = "mgs.report.exclusion.log"
    _description = "Historial de exclusiones de informe"
    _order = "changed_at desc, id desc"

    line_id = fields.Many2one("pos.order.line", "Línea de venta", required=True,
                              readonly=True, ondelete="restrict", index=True)
    order_id = fields.Many2one(related="line_id.order_id", string="Ticket", store=True,
                               readonly=True)
    was_excluded = fields.Boolean("Estado anterior", readonly=True)
    is_excluded = fields.Boolean("Estado nuevo", readonly=True)
    reason = fields.Text("Motivo", required=True, readonly=True)
    user_id = fields.Many2one("res.users", "Cambiado por", required=True, readonly=True,
                              default=lambda self: self.env.user)
    changed_at = fields.Datetime("Fecha", required=True, readonly=True,
                                 default=fields.Datetime.now)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("mgs_report_exclusion_change"):
            raise AccessError(_("El historial se crea al clasificar una línea."))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("El historial de exclusiones no se puede modificar."))

    def unlink(self):
        raise AccessError(_("El historial de exclusiones no se puede borrar."))


class MgsReportSaleReview(models.Model):
    _name = "mgs.report.sale.review"
    _description = "Línea preparada para informe"
    _order = "date_order, id"

    template_id = fields.Many2one("mgs.report.template", required=True, ondelete="cascade",
                                  index=True)
    line_id = fields.Many2one("pos.order.line", "Línea de venta", required=True,
                              ondelete="cascade", index=True)
    order_id = fields.Many2one(related="line_id.order_id", string="Ticket", readonly=True)
    date_order = fields.Datetime(related="line_id.order_id.date_order", string="Fecha", readonly=True)
    product_id = fields.Many2one(related="line_id.product_id", string="Producto", readonly=True)
    quantity = fields.Float(related="line_id.qty", string="Cantidad", readonly=True)
    amount = fields.Monetary(related="line_id.price_subtotal_incl", string="Importe con impuestos",
                             readonly=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="line_id.currency_id", readonly=True)
    excluded = fields.Boolean(related="line_id.mgs_in_b", string="En B", readonly=True)

    _sql_constraints = [
        ("mgs_report_sale_review_unique", "unique(template_id, line_id)",
         "La línea ya está preparada para esta plantilla."),
    ]

    def action_mark_excluded(self):
        return self._open_exclusion_wizard(True)

    def action_mark_included(self):
        return self._open_exclusion_wizard(False)

    def _open_exclusion_wizard(self, excluded):
        require_manager(self.env)
        return {
            "type": "ir.actions.act_window", "name": _("Clasificar línea"),
            "res_model": "mgs.report.exclusion.wizard", "view_mode": "form",
            "target": "new", "context": {
                "default_review_ids": [(6, 0, self.ids)],
                "default_excluded": excluded,
            },
        }


class MgsReportExclusionWizard(models.TransientModel):
    _name = "mgs.report.exclusion.wizard"
    _description = "Clasificar líneas para informe"

    review_ids = fields.Many2many("mgs.report.sale.review", string="Líneas", required=True)
    excluded = fields.Boolean("Excluir de los informes", required=True)
    reason = fields.Text("Motivo", required=True)

    def action_confirm(self):
        self.ensure_one()
        require_manager(self.env)
        self.review_ids.line_id.with_context(mgs_report_exclusion_change=True).action_mgs_set_report_exclusion(
            self.excluded, self.reason)
        return {"type": "ir.actions.act_window_close"}
