from odoo import fields, models, _
from odoo.exceptions import ValidationError
from .mgs_permissions import COST_GROUPS


class StockLot(models.Model):
    _inherit = "stock.lot"

    mgs_received_at = fields.Datetime("Recepción de la partida", readonly=True, copy=False)
    mgs_supplier_id = fields.Many2one("res.partner", "Proveedor", readonly=True)
    mgs_supplier_ref = fields.Char("Nº de albarán del proveedor", readonly=True)
    mgs_document_date = fields.Date("Fecha del albarán", readonly=True)
    mgs_unit_cost = fields.Float("Coste de entrada por unidad", digits="Product Price", readonly=True, groups=COST_GROUPS)
    mgs_cost_recorded = fields.Boolean("Coste histórico registrado", readonly=True, copy=False)

    def write(self, vals):
        historical = {"mgs_unit_cost", "mgs_received_at", "mgs_supplier_id", "mgs_cost_recorded",
                      "mgs_supplier_ref", "mgs_document_date"}
        if historical.intersection(vals) and any(self.mapped("mgs_cost_recorded")):
            raise ValidationError(_("El coste y origen de una partida recibida no se pueden modificar."))
        return super().write(vals)
