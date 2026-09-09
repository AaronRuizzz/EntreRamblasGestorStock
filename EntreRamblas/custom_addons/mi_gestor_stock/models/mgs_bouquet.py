# -*- coding: utf-8 -*-
"""Ramos y composiciones a medida en el mostrador.

Una floristería vende sobre todo cosas que no existen hasta que alguien las
pide: siete rosas, un poco de eucalipto y papel kraft se convierten en «Ramo,
25 €». El ticket tiene que enseñar UNA línea con su precio, pero el almacén
tiene que descontar cada tallo de su partida, con su coste real, o el margen y
el inventario dejan de valer.

Cómo funciona: el producto de la composición (p. ej. «Ramo a medida») **no es
almacenable**, así que por sí mismo no mueve stock. Lo que mueve stock son sus
componentes: por cada uno se crea un `stock.move` enlazado a la MISMA línea del
TPV (`mgs_pos_line_id`). A partir de ahí todo lo que ya existía funciona solo:
la reserva por caducidad y antigüedad (FEFO), el coste histórico congelado por
partida y el cálculo de coste de la línea, que suma todos los movimientos de la
línea sin importar de qué producto sean.

El navegador manda la composición como texto JSON en `mgs_bouquet_spec`; el
servidor la valida y crea los componentes. Nunca se confía en lo que llega: se
comprueba que los productos existen, son almacenables, son de la compañía y que
las cantidades son positivas y finitas.
"""
import json
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

# Tope de componentes por composición. Un centro de mesa grande no pasa de unos
# pocos materiales; un número enorme solo puede venir de un error o de un abuso.
MAX_COMPONENTS = 40


class ProductTemplate(models.Model):
    _inherit = "product.template"

    mgs_is_composition = fields.Boolean(
        "Ramo o composición a medida",
        help="En el TPV se elige qué lleva y el stock descuenta cada material. "
             "El producto no guarda existencias propias: las existencias son las "
             "de las flores y el material que se le pongan.")

    @api.constrains("mgs_is_composition", "is_storable")
    def _check_mgs_composition_not_storable(self):
        for template in self:
            if template.mgs_is_composition and template.is_storable:
                raise UserError(_(
                    "«%s» es una composición a medida: no puede llevar existencias "
                    "propias, porque las existencias son las de las flores que la "
                    "forman. Desmarca «Realizar un seguimiento del inventario».",
                    template.display_name))


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ["mgs_is_composition"]


class BouquetComponent(models.Model):
    _name = "mgs.bouquet.component"
    _description = "Material de una composición vendida"

    line_id = fields.Many2one("pos.order.line", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", "Material", required=True)
    quantity = fields.Float("Cantidad por unidad", required=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("El contenido de la composición lo registra el servidor al cobrar."))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("Una composición vendida no se modifica; corrígela con una devolución."))

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Una composición vendida se conserva para trazabilidad."))
        return super().unlink()


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    # Texto JSON que escribe el TPV. Se conserva tal cual como constancia de lo
    # que pidió el navegador; lo que manda son los componentes ya validados.
    mgs_bouquet_spec = fields.Char(readonly=True, copy=False)
    mgs_bouquet_ids = fields.One2many("mgs.bouquet.component", "line_id", readonly=True)

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ["mgs_bouquet_spec"]

    def _mgs_parse_bouquet(self, spec, product):
        """Convierte el JSON del navegador en componentes comprobados.

        Devuelve una lista de diccionarios lista para crear. Cualquier cosa rara
        —producto inexistente, no almacenable, de otra compañía, cantidad
        negativa o infinita— se rechaza aquí, no más adelante."""
        if not spec:
            return []
        if not product.mgs_is_composition:
            raise UserError(_("«%s» no es una composición: no puede llevar materiales.",
                              product.display_name))
        return self._mgs_parse_components(spec)

    def _mgs_parse_components(self, spec):
        """El resto de _mgs_parse_bouquet, sin el requisito de un producto
        concreto: lo usa también la línea de un evento (mgs.event.line) para
        validar su composición contra el MISMO parser que el cobro del TPV,
        sin necesitar una composición ya creada."""
        try:
            items = json.loads(spec)
        except (TypeError, ValueError):
            raise UserError(_("No se ha entendido el contenido del ramo. Vuelve a montarlo."))
        if not isinstance(items, list) or not items:
            raise UserError(_("Indica de qué está hecho el ramo antes de cobrarlo."))
        if len(items) > MAX_COMPONENTS:
            raise UserError(_("Una composición no puede llevar más de %s materiales distintos.",
                              MAX_COMPONENTS))
        grouped = {}
        for item in items:
            if not isinstance(item, dict) or type(item.get("product_id")) is not int:
                raise UserError(_("Alguno de los materiales del ramo no es válido."))
            quantity = item.get("qty")
            if type(quantity) not in (int, float) or not math.isfinite(quantity) or quantity <= 0:
                raise UserError(_("Las cantidades del ramo tienen que ser positivas."))
            grouped[item["product_id"]] = grouped.get(item["product_id"], 0.0) + float(quantity)
        products = self.env["product.product"].browse(list(grouped)).exists()
        if len(products) != len(grouped):
            raise UserError(_("Algún material del ramo ya no existe en el catálogo."))
        products.check_access("read")
        company = self.env.company
        for component in products:
            if not component.is_storable:
                raise UserError(_("«%s» no lleva control de existencias: no puede formar parte "
                                  "de un ramo.", component.display_name))
            if component.mgs_is_composition:
                raise UserError(_("Un ramo no puede llevar dentro otro ramo a medida."))
            if component.company_id and component.company_id != company:
                raise UserError(_("«%s» no es de esta tienda.", component.display_name))
        return [{"product_id": product_id, "quantity": quantity}
                for product_id, quantity in grouped.items()]

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if line.mgs_bouquet_spec:
                components = line._mgs_parse_bouquet(line.mgs_bouquet_spec, line.product_id)
                self.env["mgs.bouquet.component"].sudo().create(
                    [dict(values, line_id=line.id) for values in components])
        return lines

    def write(self, vals):
        if "mgs_bouquet_spec" in vals:
            # Mismo criterio que la marca de devolución deteriorada: una vez que
            # el stock se ha movido, el contenido del ramo es historia.
            for line in self:
                if line.mgs_move_ids or line.mgs_bouquet_ids:
                    raise UserError(_("El contenido de un ramo ya cobrado no se cambia."))
        return super().write(vals)


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def mgs_check_stock(self, session_id, lines, order_uuid=None):
        """Comprueba el stock de los materiales, no el del ramo.

        El producto «Ramo» no tiene existencias propias: si solo se mirara él, se
        cobraría un ramo sin flores suficientes. El navegador manda el contenido
        tal cual lo escribió (`bouquet_spec`) y aquí se valida con el MISMO
        parser que se usa al crear la línea, para que lo que pasa esta
        comprobación sea exactamente lo que luego se puede grabar: si el ramo
        fuese inválido, tiene que fallar ahora —antes de cobrar— y no después."""
        expanded = []
        Line = self.env["pos.order.line"]
        for line in lines if isinstance(lines, list) else []:
            expanded.append(line)
            if not isinstance(line, dict) or not line.get("bouquet_spec"):
                continue
            if type(line.get("product_id")) is not int:
                raise UserError(_("El producto no es válido."))
            product = self.env["product.product"].browse(line["product_id"]).exists()
            if not product:
                raise UserError(_("El producto ya no existe."))
            quantity = line.get("qty")
            if type(quantity) not in (int, float) or not math.isfinite(quantity):
                raise UserError(_("La cantidad no es válida."))
            for component in Line._mgs_parse_bouquet(line["bouquet_spec"], product):
                expanded.append({"product_id": component["product_id"],
                                 "qty": component["quantity"] * max(0.0, quantity)})
        return super().mgs_check_stock(session_id, expanded, order_uuid)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _create_move_from_pos_order_lines(self, lines):
        """Un movimiento por material, colgando de la línea del ramo.

        Se enlazan con `mgs_pos_line_id` a la línea de la composición: así el
        coste de la línea (`_compute_total_cost`) suma el coste real de las
        flores que se han gastado, y no el precio de venta del ramo."""
        compositions = lines.filtered(
            lambda line: line.mgs_bouquet_ids and line.qty > 0)
        if lines - compositions:
            super()._create_move_from_pos_order_lines(lines - compositions)
        for line in compositions.sorted("id"):
            for component in line.mgs_bouquet_ids.sorted("id"):
                product = component.product_id
                values = self._prepare_stock_move_vals(line, line)
                values.update({
                    "name": product.display_name,
                    "product_id": product.id,
                    "product_uom": product.uom_id.id,
                    "product_uom_qty": component.quantity * line.qty,
                    "mgs_pos_line_id": line.id,
                })
                move = self.env["stock.move"].create(values)
                move._action_confirm(merge=False)
                move._add_mls_related_to_order(line)
                move.picked = True
