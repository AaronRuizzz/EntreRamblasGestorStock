from datetime import datetime
from collections import defaultdict
import math

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero
from .mgs_permissions import COST_GROUPS, is_manager, require_operator, checked_session, \
    assert_not_maintenance


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _load_pos_data_fields(self, config_id):
        names = super()._load_pos_data_fields(config_id) + ["mgs_auto_lots"]
        return names if is_manager(self.env) else [name for name in names if name != "standard_price"]


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    mgs_unit_cost = fields.Float("Coste histórico por unidad", digits="Product Price", readonly=True, copy=False, groups=COST_GROUPS)
    mgs_cost_recorded = fields.Boolean(readonly=True, copy=False)
    mgs_return_origin_id = fields.Many2one("stock.move.line", readonly=True, copy=False, index=True)
    mgs_cost_estimated = fields.Boolean(
        "Coste estimado", readonly=True, copy=False,
        help="La cantidad viene de la partida técnica «Pendiente de revisar»: "
             "el coste es el precio de coste del producto, no el de una compra real.")

    def write(self, vals):
        if {"mgs_unit_cost", "mgs_cost_recorded", "mgs_return_origin_id"}.intersection(vals):
            if any(line.mgs_cost_recorded and line.state == "done" for line in self):
                raise ValidationError(_("El coste histórico de un movimiento terminado no se puede modificar."))
        return super().write(vals)

    def _action_done(self):
        for line in self.sudo().filtered(lambda item: not item.mgs_cost_recorded):
            cost = (line.mgs_return_origin_id.mgs_unit_cost if line.mgs_return_origin_id
                    else line.lot_id.mgs_unit_cost if line.lot_id.mgs_cost_recorded
                    else line.product_id.with_company(line.company_id).standard_price)
            line.write({"mgs_unit_cost": cost, "mgs_cost_recorded": True})
        return super()._action_done()


class StockMove(models.Model):
    _inherit = "stock.move"

    mgs_pos_line_id = fields.Many2one("pos.order.line", readonly=True, copy=False, index=True)

    def _add_mls_related_to_order(self, related_order_lines, are_qties_done=True):
        automatic = self.filtered(lambda move: move.product_id.is_storable and (move.product_id.mgs_auto_lots or move.product_id.tracking == "none")
                                 and move.location_id.usage == "internal")
        returns = self.filtered(lambda move: move.product_id.is_storable and (move.product_id.mgs_auto_lots or move.product_id.tracking == "none")
                               and move.location_id.usage == "customer")
        result = super(StockMove, self - automatic - returns)._add_mls_related_to_order(
            related_order_lines, are_qties_done=are_qties_done)
        for move in automatic.sorted(lambda m: (m.product_id.id, m.id)):
            move._do_unreserve()
            move._mgs_reserve_available_lots()
            if are_qties_done:
                move.picked = True
        for move in returns:
            move._mgs_prepare_return()
        return result

    def _mgs_prepare_return(self):
        self.ensure_one()
        self.move_line_ids.unlink()
        original = self.mgs_pos_line_id.refunded_orderline_id
        if not original or original.product_id != self.product_id:
            raise UserError(_("La devolución debe estar vinculada a la venta original."))
        sources = original.mgs_move_ids.filtered(lambda m: m.state == "done").move_line_ids
        if sources:
            self.env.cr.execute("SELECT id FROM stock_move_line WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(sources.ids)])
        remaining = self.product_uom._compute_quantity(self.product_uom_qty, self.product_id.uom_id)
        for source in sources.sorted("id"):
            returned = self.env["stock.move.line"].search([
                ("mgs_return_origin_id", "=", source.id), ("state", "!=", "cancel"),
            ])
            available = source.quantity_product_uom - sum(returned.mapped("quantity_product_uom"))
            quantity = min(remaining, max(0, available))
            if quantity <= 0:
                continue
            self.env["stock.move.line"].create({
                "move_id": self.id, "picking_id": self.picking_id.id,
                "product_id": self.product_id.id, "product_uom_id": self.product_id.uom_id.id,
                "location_id": self.location_id.id, "location_dest_id": self.location_dest_id.id,
                "lot_id": source.lot_id.id, "quantity": quantity,
                "mgs_return_origin_id": source.id,
            })
            remaining -= quantity
        if not float_is_zero(remaining, precision_rounding=self.product_id.uom_id.rounding):
            raise UserError(_("La cantidad devuelta supera la cantidad pendiente de devolución."))
        self.picked = True

    def _mgs_reserve_available_lots(self):
        self.ensure_one()
        product = self.product_id
        remaining = self.product_uom._compute_quantity(self.product_uom_qty, product.uom_id)
        quants = self.env["stock.quant"].search([
            ("product_id", "=", product.id), ("company_id", "=", self.company_id.id),
            ("location_id", "child_of", self.location_id.id),
            ("location_id.usage", "=", "internal"), ("quantity", ">", 0),
            ("owner_id", "=", False),
        ] + ([("lot_id", "!=", False)] if product.tracking != "none" else []))
        if quants:
            self.env.cr.execute("SELECT id FROM stock_quant WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(quants.ids)])
            quants.invalidate_recordset(["quantity", "reserved_quantity"])
        now = fields.Datetime.now()
        quants = quants.filtered(lambda q: not q.lot_id.expiration_date or q.lot_id.expiration_date >= now)
        quants = quants.sorted(lambda q: (
            q.lot_id.expiration_date or datetime.max,
            q.lot_id.mgs_received_at or q.in_date or datetime.max, q.id))
        for quant in quants:
            available = max(0, quant.quantity - quant.reserved_quantity)
            quantity = min(remaining, available)
            if float_is_zero(quantity, precision_rounding=product.uom_id.rounding):
                continue
            reserved = self._update_reserved_quantity(
                quantity, quant.location_id, lot_id=quant.lot_id,
                package_id=quant.package_id, owner_id=quant.owner_id, strict=True)
            remaining -= reserved
            if float_compare(remaining, 0, precision_rounding=product.uom_id.rounding) <= 0:
                break
        if float_compare(remaining, 0, precision_rounding=product.uom_id.rounding) > 0:
            if not self._mgs_reserve_deficit_fallback(remaining):
                raise UserError(_("No hay existencias disponibles sin caducar de %s. Revisa el stock antes de cobrar.", product.display_name))

    def _mgs_reserve_deficit_fallback(self, remaining):
        """Última red tras agotar las partidas válidas: solo sigue si ESTA
        venta tiene autorización de déficit para este producto (creada por
        `PosOrder.mgs_authorize_deficit` al aceptar «Añadir de todos modos»
        en el TPV). Sin esa autorización se sigue bloqueando exactamente
        igual que antes — lo que además protege mermas y eventos, que nunca
        pasan por `mgs_pos_line_id` y por tanto nunca encuentran una
        autorización con la que continuar.

        Cuando sí hay autorización, la falta se carga contra un único lote
        técnico «Pendiente de revisar» por producto (ver `mgs_stock_lot.py`),
        dejando su partida en negativo: no hay disponibilidad que reservar,
        así que la línea de movimiento se crea a mano, igual que hace
        `_mgs_prepare_return` para una devolución."""
        self.ensure_one()
        order = self.mgs_pos_line_id.order_id
        if not order:
            return False
        deficit = self.env["mgs.stock.deficit"].sudo().search([
            ("order_uuid", "=", order.uuid), ("product_id", "=", self.product_id.id),
        ], limit=1)
        if not deficit or float_compare(
                deficit.authorized_qty, 0, precision_rounding=self.product_id.uom_id.rounding) <= 0:
            return False
        lot = self.env["stock.lot"].sudo()._mgs_get_or_create_pending(self.product_id, self.company_id)
        self.env["stock.move.line"].sudo().create({
            "move_id": self.id, "picking_id": self.picking_id.id,
            "product_id": self.product_id.id, "product_uom_id": self.product_id.uom_id.id,
            "location_id": self.location_id.id, "location_dest_id": self.location_dest_id.id,
            "lot_id": lot.id, "quantity": remaining, "mgs_cost_estimated": True,
        })
        return True


class PosOrder(models.Model):
    _inherit = "pos.order"

    @api.model
    def sync_from_ui(self, orders):
        # mgs.maintenance lo pone el actualizador justo antes de copiar y
        # aplicar una actualización: sin este control, el TPV seguía
        # aceptando ventas mientras se preparaba el cambio de versión
        # (hallazgo 11). El error queda claro para quien esté cobrando.
        assert_not_maintenance(self.env)
        return super().sync_from_ui(orders)

    @api.model
    def mgs_check_stock(self, session_id, lines, order_uuid=None):
        """Comprueba disponibilidad y devuelve las faltas, no lanza excepción
        por falta de stock.

        Antes esto lanzaba `UserError` en cuanto faltaba una unidad,
        bloqueando la venta sin salida. Ahora agrega la demanda por producto
        y, para cada uno con falta, compara esa falta contra lo ya autorizado
        para ESTA venta (`mgs.stock.deficit`, ver `mgs_authorize_deficit` más
        abajo): si lo autorizado ya cubre la falta, no aparece en
        `deficits` (nada que confirmar); si no, aparece con la falta
        completa para que el TPV pida confirmación. `ok` es `True` solo
        cuando no queda ninguna falta sin autorizar.

        Sigue lanzando `UserError` para errores reales: sesión cerrada,
        caja ajena, lista o producto mal formado. Esos no son "falta de
        stock", son datos inválidos."""
        assert_not_maintenance(self.env)
        session = checked_session(self.env, session_id)
        if order_uuid:
            existing = self.search([("uuid", "=", order_uuid), ("session_id", "=", session.id)], limit=1)
            if existing.state in ("paid", "done", "invoiced") and (
                not existing.lines.filtered(lambda line: line.product_id.is_storable and line.qty)
                or (existing.picking_ids and all(p.state == "done" for p in existing.picking_ids))
            ):
                return {"ok": True, "already_confirmed": True, "deficits": []}
        if session.state != "opened":
            raise UserError(_("Abre la sesión de caja antes de cobrar."))
        if not isinstance(lines, list) or len(lines) > 500:
            raise UserError(_("La lista de productos no es válida."))
        demands = defaultdict(float)
        for line in lines:
            if not isinstance(line, dict) or type(line.get("product_id")) is not int:
                raise UserError(_("El producto no es válido."))
            quantity = line.get("qty")
            if type(quantity) not in (int, float) or not math.isfinite(quantity):
                raise UserError(_("La cantidad no es válida."))
            if quantity > 0:
                demands[line["product_id"]] += quantity
        location = session.config_id.picking_type_id.default_location_src_id
        now = fields.Datetime.now()
        deficits = []
        for product_id, quantity in demands.items():
            product = self.env["product.product"].browse(product_id).exists()
            product.check_access("read")
            if not product:
                raise UserError(_("El producto ya no existe."))
            if not product.is_storable:
                continue
            quants = self.env["stock.quant"].search([
                ("product_id", "=", product.id), ("company_id", "=", session.company_id.id),
                ("location_id", "child_of", location.id), ("location_id.usage", "=", "internal"),
                ("owner_id", "=", False),
            ])
            available = sum(max(0, q.quantity - q.reserved_quantity) for q in quants
                            if (not product.mgs_auto_lots or q.lot_id)
                            and (not q.lot_id.expiration_date or q.lot_id.expiration_date >= now))
            rounding = product.uom_id.rounding
            missing = quantity - available
            if float_compare(missing, 0, precision_rounding=rounding) <= 0:
                continue
            authorized = 0.0
            if order_uuid:
                deficit = self.env["mgs.stock.deficit"].sudo().search([
                    ("order_uuid", "=", order_uuid), ("product_id", "=", product.id),
                ], limit=1)
                authorized = deficit.authorized_qty if deficit else 0.0
            if float_compare(missing - authorized, 0, precision_rounding=rounding) > 0:
                deficits.append({
                    "product_id": product.id, "product_name": product.display_name,
                    "available": available, "requested": quantity,
                    "missing": missing, "authorized": authorized,
                })
        return {"ok": not deficits, "already_confirmed": False, "deficits": deficits}

    @api.model
    def mgs_authorize_deficit(self, session_id, order_uuid, lines):
        """Registra que la dependienta ha aceptado «Añadir de todos modos»
        para las faltas actuales de `lines` en la venta `order_uuid`, y deja
        un aviso de stock enlazado al ticket. Devuelve el resultado de volver
        a comprobar: si algo cambió entre medias (otra caja se llevó el
        último lote, p. ej.), `ok` seguirá en `False` y el TPV lo notará."""
        require_operator(self.env)
        if not order_uuid or not isinstance(order_uuid, str):
            raise UserError(_("Falta el identificador de la venta."))
        session = checked_session(self.env, session_id)
        result = self.mgs_check_stock(session_id, lines, order_uuid)
        Deficit = self.env["mgs.stock.deficit"].sudo()
        for entry in result.get("deficits", []):
            product = self.env["product.product"].browse(entry["product_id"])
            Deficit._mgs_upsert(order_uuid, session, product, entry["missing"])
            self.env["mgs.stock.alert.notice"].sudo().create({
                "product_id": product.product_tmpl_id.id,
                "name": _("%(prod)s: venta %(ref)s con stock insuficiente — revisar",
                          prod=product.display_name, ref=order_uuid[:8]),
                "pos_order_uuid": order_uuid, "session_id": session.id,
            })
        return self.mgs_check_stock(session_id, lines, order_uuid)

    @api.model
    def _process_order(self, order, existing_order):
        session = checked_session(self.env, order["session_id"])
        if session.state != "opened":
            raise UserError(_("La sesión de caja no está abierta. Revisa las ventas pendientes antes de cerrar."))
        order_id = super()._process_order(order, existing_order)
        # Reconciliación: al autorizar el déficit el ticket todavía no existe
        # como pos.order (solo hay uuid). En cuanto se sincroniza de verdad,
        # se enlaza aquí para poder abrir el ticket desde el aviso de stock.
        uuid = order.get("uuid")
        if uuid and order_id:
            self.env["mgs.stock.deficit"].sudo().search([
                ("order_uuid", "=", uuid), ("pos_order_id", "=", False),
            ]).write({"pos_order_id": order_id})
            self.env["mgs.stock.alert.notice"].sudo().search([
                ("pos_order_uuid", "=", uuid), ("pos_order_id", "=", False),
            ]).write({"pos_order_id": order_id})
        return order_id

    def _should_create_picking_real_time(self):
        return True

    def _create_order_picking(self):
        require_operator(self.env)
        self.check_access("write")
        result = super(PosOrder, self.sudo())._create_order_picking()
        if self.lines.filtered(lambda line: line.product_id.is_storable and line.qty):
            if not self.picking_ids or any(p.state != "done" for p in self.picking_ids):
                raise UserError(_("No se pudo confirmar el movimiento de stock. La venta no se ha completado."))
        return result


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    mgs_move_ids = fields.One2many("stock.move", "mgs_pos_line_id", readonly=True)

    def _compute_total_cost(self, stock_moves):
        self = self.sudo()
        automatic = self.filtered(lambda line: line.mgs_move_ids or line.product_id.mgs_auto_lots)
        super(PosOrderLine, self - automatic)._compute_total_cost(stock_moves)
        for line in automatic:
            moves = line.mgs_move_ids.filtered(lambda move: move.state == "done")
            if not moves:
                continue
            cost = sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in moves.move_line_ids)
            line.total_cost = line.company_id.currency_id._convert(
                cost if line.qty >= 0 else -cost, line.currency_id, line.company_id,
                line.order_id.date_order or fields.Date.today(), round=False)
            line.is_total_cost_computed = True


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _create_move_from_pos_order_lines(self, lines):
        automatic = lines.filtered(lambda line: line.product_id.is_storable and (line.product_id.mgs_auto_lots or line.product_id.tracking == "none"))
        if lines - automatic:
            super()._create_move_from_pos_order_lines(lines - automatic)
        for line in automatic.sorted(lambda item: (item.product_id.id, item.id)):
            values = self._prepare_stock_move_vals(line, line)
            values["mgs_pos_line_id"] = line.id
            move = self.env["stock.move"].create(values)
            move._action_confirm(merge=False)
            move._add_mls_related_to_order(line)
            move.picked = True
