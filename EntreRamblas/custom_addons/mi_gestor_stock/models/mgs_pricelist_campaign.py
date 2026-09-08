# -*- coding: utf-8 -*-
"""Tarifa de campaña: la rosa cuesta distinto en San Valentín, sin tocar la
ficha del producto a mano.

Se apoya en `product.pricelist` nativo, ya soportado por el TPV de serie —
no hay nada que reinventar. Este asistente es solo la capa simple encima: la
propietaria nunca ve el formulario nativo con sus cuatro modos de cálculo ni
la base recursiva de otra tarifa.

Comprobado que no interfiere con lo que ya existe:
  - El margen sigue siendo correcto: `_compute_total_cost` (mgs_pos_stock.py)
    suma el coste histórico de la partida, nunca mira el precio de venta.
  - El ramo a medida conserva su precio manual: `pos_store.js` marca
    `price_type: "manual"` en cuanto la línea trae `price_unit` (que
    pos_bouquet.js siempre manda), y solo recalcula al cambiar de tarifa las
    líneas `"original"`.
  - El ticket fiscal sigue cuadrando: `_mgs_pos_ticket` (mgs_config.py)
    recalcula el IVA desde los subtotales reales de cada línea, sea cual sea
    la tarifa o el descuento aplicados.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .mgs_permissions import require_manager


class MgsPricelistCampaign(models.TransientModel):
    _name = "mgs.pricelist.campaign"
    _description = "Tarifa de campaña"

    name = fields.Char("Nombre de la tarifa", required=True)
    date_start = fields.Datetime("Desde", required=True)
    date_end = fields.Datetime("Hasta", required=True)
    categ_id = fields.Many2one(
        "product.category", "Solo esta categoría",
        help="Vacío = se aplica a todo el catálogo.")
    compute_price = fields.Selection([
        ("discount", "Descuento (%)"),
        ("fixed", "Precio fijo"),
    ], default="discount", required=True,
        help="Descuento: se cobra menos, un porcentaje del precio de venta. "
             "Precio fijo: se cobra exactamente el precio que se indique "
             "(sirve tanto para bajar como para subir el precio).")
    percent_price = fields.Float("Descuento (%)", default=10.0)
    fixed_price = fields.Float("Precio fijo", digits="Product Price")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "date_start" in fields_list and "date_start" not in res:
            res["date_start"] = fields.Datetime.now()
        return res

    def action_create(self):
        self.ensure_one()
        require_manager(self.env)
        if not self.date_end or not self.date_start or self.date_end <= self.date_start:
            raise UserError(_("La fecha final tiene que ser posterior a la inicial."))

        item_vals = {
            "applied_on": "2_product_category" if self.categ_id else "3_global",
            "categ_id": self.categ_id.id if self.categ_id else False,
            "date_start": self.date_start, "date_end": self.date_end,
        }
        if self.compute_price == "fixed":
            if self.fixed_price <= 0:
                raise UserError(_("Indica un precio fijo mayor que cero."))
            item_vals.update({"compute_price": "fixed", "fixed_price": self.fixed_price})
        else:
            if self.percent_price <= 0:
                raise UserError(_("El descuento tiene que ser mayor que cero."))
            item_vals.update({"compute_price": "percentage", "percent_price": self.percent_price})

        pricelist = self.env["product.pricelist"].create({
            "name": self.name,
            "item_ids": [(0, 0, item_vals)],
        })
        # Disponible de inmediato en la caja, sin pasos extra: activar tarifas
        # y añadir esta a las disponibles. No se fija como la tarifa por
        # defecto: se elige a mano en el TPV cuando toque la campaña.
        configs = self.env["pos.config"].search([("company_id", "=", self.env.company.id)])
        configs.write({
            "use_pricelist": True,
            "available_pricelist_ids": [(4, pricelist.id)],
        })
        return {
            "type": "ir.actions.act_window", "res_model": "product.pricelist",
            "res_id": pricelist.id, "view_mode": "form", "target": "current",
        }
