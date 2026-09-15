from odoo import api, fields, models, _
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
    mgs_pending_review = fields.Boolean(
        "Pendiente de revisar", readonly=True, copy=False,
        help="Partida técnica sin coste ni origen real: recoge lo que se ha "
             "vendido por encima de las existencias con autorización expresa. "
             "Su coste es estimado (precio de coste del producto) hasta que "
             "se revise a mano.")

    def write(self, vals):
        historical = {"mgs_unit_cost", "mgs_received_at", "mgs_supplier_id", "mgs_cost_recorded",
                      "mgs_supplier_ref", "mgs_document_date"}
        if historical.intersection(vals) and any(self.mapped("mgs_cost_recorded")):
            raise ValidationError(_("El coste y origen de una partida recibida no se pueden modificar."))
        return super().write(vals)

    @api.model
    def _mgs_get_or_create_pending(self, product, company):
        """Un único lote técnico «Pendiente de revisar» reutilizable por
        producto (no uno nuevo por venta): así la responsable tiene un solo
        sitio por producto donde revisar y costear lo vendido de más."""
        self.env.cr.execute("SELECT id FROM product_product WHERE id = %s FOR UPDATE", [product.id])
        lot = self.search([
            ("product_id", "=", product.id), ("company_id", "=", company.id),
            ("mgs_pending_review", "=", True),
        ], limit=1)
        if lot:
            return lot
        return self.create({
            "product_id": product.id, "company_id": company.id,
            "name": _("Pendiente de revisar"), "mgs_pending_review": True,
        })
