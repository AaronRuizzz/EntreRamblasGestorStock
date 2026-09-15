from odoo import api, fields, models
from odoo.tools.float_utils import float_compare


class MgsStockDeficit(models.Model):
    """Autorización para vender por debajo de existencias.

    Cuando la dependienta acepta «Añadir de todos modos» ante un producto sin
    stock suficiente, se guarda aquí cuánto se ha autorizado a faltar para
    ESA venta y ESE producto (`order_uuid` + `product_id`), con quién y
    cuándo. `PosOrder.mgs_check_stock` compara la falta real contra lo ya
    autorizado: si la cantidad sube después de aceptar (más unidades, más
    materiales de un ramo...), la falta supera lo autorizado y se vuelve a
    pedir confirmación — aceptar una vez no autoriza faltas posteriores."""
    _name = "mgs.stock.deficit"
    _description = "Autorización de venta con stock insuficiente"
    _order = "id desc"

    order_uuid = fields.Char(required=True, index=True)
    session_id = fields.Many2one("pos.session", required=True, ondelete="cascade")
    pos_order_id = fields.Many2one("pos.order", ondelete="set null", copy=False)
    product_id = fields.Many2one("product.product", required=True, ondelete="cascade")
    authorized_qty = fields.Float("Cantidad autorizada de más", required=True)
    user_id = fields.Many2one("res.users", readonly=True)
    authorized_at = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("mgs_stock_deficit_unique", "unique(order_uuid, product_id)",
         "Ya existe una autorización de stock para este producto en esta venta."),
    ]

    @api.model
    def _mgs_upsert(self, order_uuid, session, product, qty):
        """Crea o amplía la autorización para `order_uuid`+`product`.

        Bloquea primero la caja (una sola caja por tienda: coste de bloqueo
        despreciable, mismo idioma que `mgs_reception.py`/`mgs_event.py`) para
        que dos peticiones casi simultáneas de la misma sesión se ejecuten
        una detrás de otra y nunca creen dos filas para el mismo par
        venta+producto. `authorized_qty` solo crece (máximo entre lo que
        había y lo nuevo): es un tope acumulado, no se reduce solo."""
        self.env.cr.execute("SELECT id FROM pos_session WHERE id = %s FOR UPDATE", [session.id])
        existing = self.search([
            ("order_uuid", "=", order_uuid), ("product_id", "=", product.id),
        ], limit=1)
        if existing:
            if float_compare(qty, existing.authorized_qty,
                             precision_rounding=product.uom_id.rounding) > 0:
                existing.write({
                    "authorized_qty": qty, "user_id": self.env.uid,
                    "authorized_at": fields.Datetime.now(),
                })
            return existing
        return self.create({
            "order_uuid": order_uuid, "session_id": session.id, "product_id": product.id,
            "authorized_qty": qty, "user_id": self.env.uid, "authorized_at": fields.Datetime.now(),
        })
