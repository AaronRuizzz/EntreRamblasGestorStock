# -*- coding: utf-8 -*-
"""Baja asistida de caducados: el automatismo DETECTA, la persona CONFIRMA.

Hoy nada da de baja lo caducado solo: el cron de mgs_stock_alert.py avisa,
pero lo caducado sigue contando en qty_available (solo se excluye al vender,
en mgs_pos_stock.py) y sigue valorado en el informe mensual. Un cron que diera
de baja por su cuenta sería peligroso: `stock.scrap.do_scrap()` es
IRREVERSIBLE, y un PC de tienda puede llevar días sin abrirse, así que nadie
habría podido revisar qué se iba a tirar antes de que ocurriera.

Por eso el cron solo genera o refresca una PROPUESTA (una por tienda, siempre
la misma mientras siga abierta): una lista de qué está caducado y hace cuánto,
con el coste que se va a dar de baja a la vista ANTES de confirmar. Confirmar
exige a la propietaria y vuelve a comprobar que el stock no ha cambiado desde
que se generó la propuesta (mismo patrón que mgs_inventory_count.py). Un error
se corrige con un recuento físico, igual que ya se documenta para el resto de
ajustes de esta familia — no hay «deshacer» porque no hay commit a medias.
"""
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .mgs_permissions import require_manager


class MgsExpiryWriteoff(models.Model):
    _name = "mgs.expiry.writeoff"
    _description = "Baja de caducados"
    _order = "detected_at desc"

    name = fields.Char(readonly=True, copy=False, default=lambda self: _("Nuevo"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    state = fields.Selection([
        ("proposed", "Propuesta"),
        ("confirmed", "Confirmada"),
        ("cancelled", "Cancelada"),
    ], default="proposed", required=True, readonly=True, copy=False)
    detected_at = fields.Datetime(readonly=True, default=fields.Datetime.now, copy=False)
    confirmed_at = fields.Datetime(readonly=True, copy=False)
    confirmed_by = fields.Many2one("res.users", readonly=True, copy=False)
    line_ids = fields.One2many("mgs.expiry.writeoff.line", "writeoff_id", string="Partidas", readonly=True)
    total_cost = fields.Float(compute="_compute_total_cost", store=True, digits="Product Price")

    @api.depends("line_ids.quantity", "line_ids.unit_cost")
    def _compute_total_cost(self):
        for writeoff in self:
            writeoff.total_cost = sum(line.quantity * line.unit_cost for line in writeoff.line_ids)

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            vals["name"] = self.env["ir.sequence"].next_by_code("mgs.expiry.writeoff") or _("Nuevo")
        return super().create(vals_list)

    def unlink(self):
        require_manager(self.env)
        if any(writeoff.state == "confirmed" for writeoff in self):
            raise UserError(_("Una baja ya confirmada se conserva para trazabilidad."))
        return super().unlink()

    def _lock(self):
        require_manager(self.env)
        self.ensure_one()
        self.check_access("write")
        if self.company_id != self.env.company:
            raise UserError(_("Esta propuesta no es de esta tienda."))
        self.env.cr.execute("SELECT id FROM mgs_expiry_writeoff WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()

    def action_confirm(self):
        """Da de baja lo de la propuesta, línea a línea, solo si el stock
        de cada una sigue siendo el que se vio al generarla."""
        self._lock()
        if self.state != "proposed":
            raise UserError(_("Solo se confirma una propuesta pendiente."))
        if not self.line_ids:
            raise UserError(_("No hay nada que dar de baja en esta propuesta."))

        self.env.cr.execute(
            "SELECT id FROM stock_quant WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(self.line_ids.mgs_quant_id.ids)])
        for line in self.line_ids:
            quant = line.mgs_quant_id.exists()
            quant.invalidate_recordset(["write_date"])
            if not quant or quant.write_date != line.snapshot_write_date:
                raise UserError(_(
                    "El stock de «%s» ha cambiado desde que se generó esta "
                    "propuesta (una venta, un recuento...). Cancélala y "
                    "genera una nueva antes de confirmar.",
                    line.product_id.display_name))

        for line in self.line_ids:
            scrap = self.env["stock.scrap"].sudo().with_context(_mgs_expiry_line=line).create({
                "product_id": line.product_id.id, "product_uom_id": line.product_id.uom_id.id,
                "scrap_qty": line.quantity, "lot_id": line.lot_id.id,
                "location_id": line.location_id.id, "company_id": self.company_id.id,
                "origin": self.name, "mgs_reason": "expiry", "mgs_expiry_line_id": line.id,
            })
            scrap.do_scrap()
            super(MgsExpiryWriteoffLine, line).write({"scrap_id": scrap.id})
        super(MgsExpiryWriteoff, self).write({
            "state": "confirmed", "confirmed_at": fields.Datetime.now(), "confirmed_by": self.env.user.id,
        })
        return True

    def action_cancel(self):
        self._lock()
        if self.state != "proposed":
            raise UserError(_("Solo se cancela una propuesta pendiente."))
        super(MgsExpiryWriteoff, self).write({"state": "cancelled"})
        return True

    # ------------------------------------------------------------------
    # Cron: detecta y refresca, nunca confirma solo.
    # ------------------------------------------------------------------
    @api.model
    def _mgs_cron_detect_expired(self):
        for company in self.env["res.company"].search([]):
            self.sudo().with_company(company)._mgs_refresh_proposal()

    def _mgs_refresh_proposal(self):
        """Recalcula, de cero, las partidas de la propuesta abierta de esta
        compañía (o la crea si hace falta). Idempotente a propósito: cada
        pase del cron reemplaza el contenido por la realidad actual, nunca
        acumula ni duplica."""
        company = self.env.company
        grace_days = self.env["mgs.config"]._mgs_get().expiry_grace_days
        cutoff = fields.Datetime.now() - timedelta(days=max(0, grace_days))
        quants = self.env["stock.quant"].search([
            ("company_id", "=", company.id), ("location_id.usage", "=", "internal"),
            ("owner_id", "=", False), ("quantity", ">", 0),
            ("lot_id.expiration_date", "!=", False), ("lot_id.expiration_date", "<", cutoff),
        ])
        proposal = self.search([("company_id", "=", company.id), ("state", "=", "proposed")], limit=1)
        if not quants:
            if proposal:
                proposal.line_ids.unlink()
            return proposal
        if not proposal:
            proposal = self.create({"company_id": company.id})
        proposal.line_ids.unlink()
        self.env["mgs.expiry.writeoff.line"].create([{
            "writeoff_id": proposal.id,
            "product_id": quant.product_id.id, "lot_id": quant.lot_id.id,
            "location_id": quant.location_id.id, "quantity": quant.quantity,
            "unit_cost": (quant.lot_id.mgs_unit_cost if quant.lot_id.mgs_cost_recorded
                         else quant.product_id.with_company(company).standard_price),
            "snapshot_write_date": quant.write_date,
            "mgs_quant_id": quant.id,
        } for quant in quants])
        proposal.detected_at = fields.Datetime.now()
        return proposal


class MgsExpiryWriteoffLine(models.Model):
    _name = "mgs.expiry.writeoff.line"
    _description = "Partida de una baja de caducados"

    writeoff_id = fields.Many2one("mgs.expiry.writeoff", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="writeoff_id.company_id", store=True)
    product_id = fields.Many2one("product.product", "Producto", required=True)
    lot_id = fields.Many2one("stock.lot", "Partida", required=True)
    location_id = fields.Many2one("stock.location", "Ubicación", required=True)
    quantity = fields.Float("Cantidad", required=True)
    unit_cost = fields.Float("Coste unitario", digits="Product Price")
    subtotal = fields.Float(compute="_compute_subtotal", store=True, string="Coste")
    # Foto del quant en el momento de la propuesta: si no coincide al
    # confirmar, algo se movió y hay que rehacer la propuesta antes de dar
    # nada de baja (ver action_confirm). No es un campo de negocio, es la
    # comprobación de concurrencia — de ahí que no tenga traducción visible.
    snapshot_write_date = fields.Datetime(readonly=True)
    scrap_id = fields.Many2one("stock.scrap", readonly=True, copy=False)
    # No se guarda como campo normal expuesto: es la referencia interna al
    # quant que se comprobó, solo la usa action_confirm/_mgs_refresh_proposal.
    mgs_quant_id = fields.Many2one("stock.quant", readonly=True, copy=False)

    @api.depends("quantity", "unit_cost")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost

    def write(self, vals):
        if not self.env.su and (set(vals) - {"scrap_id"}):
            raise AccessError(_("Una partida de la propuesta no se edita a mano; regenera la propuesta."))
        return super().write(vals)

    def unlink(self):
        # _mgs_refresh_proposal() SÍ necesita poder vaciar las líneas de una
        # propuesta aún en 'proposed' (las recalcula de cero en cada pase del
        # cron); lo que no puede pasar es borrar el rastro de una ya
        # confirmada, aunque sea por RPC directo sobre la línea sin pasar por
        # el asistente (que ya lo impide en su propio unlink()).
        if any(line.writeoff_id.state == "confirmed" for line in self):
            raise UserError(_("Una baja ya confirmada se conserva para trazabilidad."))
        return super().unlink()


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    mgs_expiry_line_id = fields.Many2one(
        "mgs.expiry.writeoff.line", "Baja de caducados", readonly=True, copy=False)
    _sql_constraints = [
        ("mgs_expiry_line_unique", "unique(mgs_expiry_line_id)",
         "Esta partida de la propuesta ya tiene una merma vinculada."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        source = self.env.context.get("_mgs_expiry_line")
        for vals in vals_list:
            if vals.get("mgs_expiry_line_id") and not (
                    isinstance(source, models.BaseModel) and source._name == "mgs.expiry.writeoff.line"
                    and source.id == vals["mgs_expiry_line_id"]):
                raise AccessError(_("El servidor vincula la merma a la propuesta de caducados."))
        return super().create(vals_list)

    def write(self, vals):
        if "mgs_expiry_line_id" in vals:
            raise AccessError(_("No se puede cambiar el origen de la merma."))
        return super().write(vals)
