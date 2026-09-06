from odoo import fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from .mgs_permissions import require_operator


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    mgs_reason = fields.Selection([
        ("deterioration", "Deterioro"), ("expiry", "Caducidad"),
        ("breakage", "Rotura"), ("return", "Devolución no recuperable"),
    ], string="Motivo", required=True, default="deterioration")
    mgs_validated_by = fields.Many2one("res.users", "Registrado por", readonly=True, copy=False)

    def do_scrap(self):
        self.ensure_one()
        require_operator(self.env)
        self.check_access("write")
        self.env.cr.execute("SELECT id FROM stock_scrap WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["state"])
        if self.state == "done":
            return True
        if self.scrap_qty <= 0:
            raise UserError(_("La cantidad de merma debe ser positiva."))
        if self.product_id.tracking != "none" and not self.lot_id:
            raise UserError(_("Selecciona la partida de la mercancía que se da de baja."))
        quants = self.env["stock.quant"]._gather(
            self.product_id, self.location_id, lot_id=self.lot_id,
            package_id=self.package_id, owner_id=self.owner_id, strict=True)
        if quants:
            self.env.cr.execute("SELECT id FROM stock_quant WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(quants.ids)])
            quants.invalidate_recordset(["quantity", "reserved_quantity"])
        available = sum(q.quantity - q.reserved_quantity for q in quants)
        needed = self.product_uom_id._compute_quantity(self.scrap_qty, self.product_id.uom_id)
        if float_compare(available, needed, precision_rounding=self.product_id.uom_id.rounding) < 0:
            raise UserError(_("No hay suficiente stock disponible de esta partida para registrar la merma."))
        result = super(StockScrap, self.sudo()).do_scrap()
        self.mgs_validated_by = self.env.user
        return result
