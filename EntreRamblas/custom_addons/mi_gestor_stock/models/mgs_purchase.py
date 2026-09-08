# -*- coding: utf-8 -*-
"""Pedidos a proveedor: qué se ha pedido y qué falta por llegar.

Deliberadamente NO se usa el módulo nativo `purchase` (ni `purchase_stock`).
Sus albaranes de entrada se generan por rutas de almacén, sin pasar por
`mgs.reception.action_confirm`, que es el único sitio donde nace una partida
con `mgs_unit_cost` / `mgs_supplier_id` / `mgs_cost_recorded` congelados. Con
`purchase_stock` los lotes recibidos quedarían sin ese coste histórico, y todo
el margen del informe mensual empezaría a mentir en silencio. También traería
su propio menú raíz, facturas de proveedor y un flujo completo (RFQ, portal,
recordatorios) que aquí es ruido: lo único que hace falta es saber qué se ha
pedido y qué sigue sin llegar.

La recepción de mercancía sigue siendo, como siempre, `mgs.reception`: aquí
solo se lleva la cuenta de lo pedido y lo recibido por línea. Un pedido no
mueve stock por sí mismo — eso solo pasa al recibirlo de verdad.
"""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError

from .mgs_permissions import require_manager


class MgsPurchaseOrder(models.Model):
    _name = "mgs.purchase.order"
    _description = "Pedido a proveedor"
    _order = "order_date desc, id desc"

    name = fields.Char(readonly=True, copy=False, default=lambda self: _("Nuevo"))
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one("res.partner", "Proveedor", required=True)
    order_date = fields.Date("Fecha del pedido", default=fields.Date.context_today, required=True)
    expected_date = fields.Date("Entrega prevista")
    state = fields.Selection([
        ("draft", "Borrador"),
        ("ordered", "Pedido"),
        ("partial", "Recibido en parte"),
        ("received", "Recibido"),
        ("cancelled", "Cancelado"),
    ], default="draft", required=True, readonly=True, copy=False)
    line_ids = fields.One2many("mgs.purchase.order.line", "order_id", string="Partidas")
    note = fields.Text("Notas")
    amount_total = fields.Float(compute="_compute_amount_total", store=True, digits="Product Price")

    @api.depends("line_ids.quantity", "line_ids.unit_cost")
    def _compute_amount_total(self):
        for order in self:
            order.amount_total = sum(line.quantity * line.unit_cost for line in order.line_ids)

    # ------------------------------------------------------------------
    # Blindaje: igual que mgs.event, solo la propietaria y por los sitios
    # que corresponde (create con lista blanca de campos; el estado y lo
    # recibido cambian solo a través de las acciones de más abajo).
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            forbidden = set(vals) - {"partner_id", "order_date", "expected_date",
                                     "line_ids", "note", "company_id"}
            if forbidden:
                raise AccessError(_("El estado de un pedido lo cambia el propio flujo, no se escribe a mano."))
            vals["name"] = self.env["ir.sequence"].next_by_code("mgs.purchase.order") or _("Nuevo")
        return super().create(vals_list)

    def write(self, vals):
        # Sin gating por env.su: la regla es de integridad del flujo, no un
        # permiso que se pueda saltar por ser superusuario. Las transiciones
        # internas (action_confirm, action_cancel, _mgs_register_receipt) se
        # saltan ESTE write llamando a super(MgsPurchaseOrder, self).write(...)
        # directamente, igual que hace mgs.event.py con sus líneas.
        require_manager(self.env)
        if "state" in vals:
            raise AccessError(_(
                "El estado del pedido lo cambia el propio flujo "
                "(Confirmar / Cancelar), no se escribe a mano."))
        if any(order.state != "draft" for order in self) and (set(vals) - {"note", "expected_date"}):
            raise UserError(_(
                "Un pedido ya confirmado no se edita: cancélalo y crea otro "
                "si hace falta cambiar algo. Así queda constancia de lo que "
                "se pidió de verdad."))
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        if any(order.state != "draft" for order in self):
            raise UserError(_("Los pedidos confirmados se conservan para trazabilidad; cancélalos en vez de borrarlos."))
        return super().unlink()

    def _lock(self):
        require_manager(self.env)
        self.ensure_one()
        self.check_access("write")
        if self.company_id != self.env.company:
            raise UserError(_("El pedido no es de esta tienda."))
        self.env.cr.execute("SELECT id FROM mgs_purchase_order WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()

    # ------------------------------------------------------------------
    # Recorrido: borrador -> pedido -> (recibido en parte) -> recibido
    #                                -> cancelado
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Pasa el pedido a «Pedido»: ya se ha mandado al proveedor.

        No mueve ni un gramo de stock — eso solo ocurre al recibirlo de
        verdad, por `mgs.reception`. Esto es solo el papel."""
        self._lock()
        if self.state == "ordered":
            return True
        if self.state != "draft":
            raise UserError(_("Solo se confirma un pedido en borrador."))
        if not self.line_ids:
            raise UserError(_("Añade al menos una partida al pedido."))
        for line in self.line_ids:
            if line.quantity <= 0:
                raise UserError(_("Las cantidades del pedido tienen que ser positivas."))
        super(MgsPurchaseOrder, self).write({"state": "ordered"})
        return True

    def action_cancel(self):
        self._lock()
        if self.state == "received":
            raise UserError(_("Un pedido ya recibido del todo no se cancela."))
        super(MgsPurchaseOrder, self).write({"state": "cancelled"})
        return True

    def action_receive(self):
        """Abre Recepción con este pedido precargado: proveedor y coste
        previsto ya rellenos, sin tener que volver a escribirlos."""
        self.ensure_one()
        if self.state not in ("ordered", "partial"):
            raise UserError(_("Este pedido todavía no se ha confirmado, o ya está recibido."))
        wizard = self.env["mgs.reception"].create({
            "purchase_id": self.id, "supplier_id": self.partner_id.id,
        })
        return {
            "type": "ir.actions.act_window", "res_model": "mgs.reception",
            "view_mode": "form", "res_id": wizard.id, "target": "current",
        }

    def _mgs_register_receipt(self, product_quantities):
        """Suma lo recibido a las líneas que hagan pareja por producto.

        Llamado por `mgs.reception.action_confirm()`, YA dentro del mismo
        candado que esa acción toma sobre `product_product`; aquí se toma
        además el candado de este pedido (mismo orden en los dos sitios:
        producto primero, pedido después) para que dos recepciones a la vez
        contra el mismo pedido no se pisen sumando sobre un valor ya viejo.

        `product_quantities`: {product_id: cantidad recibida ahora}."""
        self._lock()
        by_product = {}
        for line in self.line_ids:
            by_product.setdefault(line.product_id.id, self.env["mgs.purchase.order.line"])
            by_product[line.product_id.id] |= line
        for product_id, qty in product_quantities.items():
            lines = by_product.get(product_id)
            if not lines:
                continue
            remaining = qty
            for line in lines.sorted("id"):
                if remaining <= 0:
                    break
                pending = max(0.0, line.quantity - line.received_qty)
                take = min(pending, remaining)
                if take > 0:
                    super(MgsPurchaseOrderLine, line).write({"received_qty": line.received_qty + take})
                    remaining -= take
            if remaining > 0:
                # Ha llegado más de lo pedido de ese producto: se apunta en
                # la primera línea, para que no se pierda de la cuenta.
                first = lines.sorted("id")[0]
                super(MgsPurchaseOrderLine, first).write(
                    {"received_qty": first.received_qty + remaining})
        if self.line_ids and all(line.received_qty >= line.quantity for line in self.line_ids):
            new_state = "received"
        elif any(line.received_qty > 0 for line in self.line_ids):
            new_state = "partial"
        else:
            new_state = self.state
        if new_state != self.state:
            super(MgsPurchaseOrder, self).write({"state": new_state})


class MgsPurchaseOrderLine(models.Model):
    _name = "mgs.purchase.order.line"
    _description = "Partida de un pedido a proveedor"

    order_id = fields.Many2one("mgs.purchase.order", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    product_id = fields.Many2one("product.product", "Producto", required=True)
    quantity = fields.Float("Cantidad pedida", default=1.0, required=True)
    unit_cost = fields.Float("Coste unitario previsto", digits="Product Price")
    received_qty = fields.Float("Recibido", readonly=True, copy=False)
    pending_qty = fields.Float(compute="_compute_pending_qty", string="Pendiente")
    subtotal = fields.Float(compute="_compute_subtotal", store=True, string="Importe")

    @api.depends("quantity", "received_qty")
    def _compute_pending_qty(self):
        for line in self:
            line.pending_qty = max(0.0, line.quantity - line.received_qty)

    @api.depends("quantity", "unit_cost")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_cost

    def write(self, vals):
        # Sin gating por env.su, mismo motivo que en MgsPurchaseOrder.write():
        # _mgs_register_receipt() se salta ESTE write con
        # super(MgsPurchaseOrderLine, line).write(...) a propósito.
        if "received_qty" in vals:
            raise AccessError(_("Lo recibido lo actualiza la propia recepción, no se escribe a mano."))
        # El formulario ya bloquea las partidas en cuanto el pedido deja el
        # borrador (line_ids readonly); esto cierra la misma vía por RPC
        # directo sobre la línea, sin pasar por el pedido.
        if any(line.order_id.state != "draft" for line in self) and (set(vals) - {"received_qty"}):
            raise UserError(_(
                "Un pedido ya confirmado no se edita: cancélalo y crea otro "
                "si hace falta cambiar algo."))
        return super().write(vals)
