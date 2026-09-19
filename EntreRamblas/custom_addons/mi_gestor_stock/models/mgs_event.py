# -*- coding: utf-8 -*-
"""Eventos y encargos: presupuesto → señal → entrega → devolución → cobro.

Un evento (boda, bautizo, comunión, empresa...) no cabe en el TPV: se cierra
semanas antes, lleva señal, y una parte del material —arcos, candelabros,
columnas— **se alquila**: sale de la tienda y tiene que volver. Este módulo es
el documento que sostiene todo eso.

Dos ideas que conviene entender antes de tocar nada:

1. **Reservar no es entregar.** Al aceptar el presupuesto el material queda
   comprometido para esa fecha, pero sigue físicamente en la tienda: no se mueve
   ni una unidad de stock. El movimiento real ocurre el día de la entrega. Por
   eso la disponibilidad de alquiler no se puede mirar con `qty_available`: hay
   que contar la flota entera y restarle lo que ya está comprometido en fechas
   que se solapan.

2. **Lo alquilado sigue siendo nuestro.** Cuando sale al evento va a una
   ubicación de tránsito, no a «cliente»: no está en la tienda (no se puede
   vender) pero no se ha vendido. Lo que vuelve entero regresa al almacén; lo
   que vuelve roto se da de baja como merma con su coste real; lo que no vuelve
   se queda a la vista en la ubicación de alquiler para poder reclamarlo.
"""
import json
import math
from urllib.parse import urlencode

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare, float_is_zero
from .mgs_permissions import require_manager

RENTAL_LOCATION = "mi_gestor_stock.stock_location_rental"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    mgs_rental_ok = fields.Boolean(
        "Se alquila",
        help="Sale al evento y vuelve. No se cobra como venta: se reserva por "
             "fechas y hay que registrar su devolución.")
    mgs_rental_deposit = fields.Float(
        "Fianza por unidad", digits="Product Price",
        help="Importe que se pide en depósito por cada unidad que sale. "
             "Es informativo: sirve para calcular la fianza del evento.")

    @api.constrains("mgs_rental_ok", "is_storable")
    def _check_mgs_rental_is_storable(self):
        for template in self:
            if template.mgs_rental_ok and not template.is_storable:
                raise UserError(_(
                    "«%s» se alquila, así que hace falta llevarle la cuenta de "
                    "unidades: marca «Realizar un seguimiento del inventario».",
                    template.display_name))


class ProductProduct(models.Model):
    _inherit = "product.product"

    def mgs_rental_fleet(self):
        """Unidades que son nuestras, estén en la tienda o fuera en un evento.

        No vale `qty_available`: lo que está fuera alquilado no cuenta ahí, y
        sin embargo sigue siendo nuestro y volverá."""
        self.ensure_one()
        rental = self.env.ref(RENTAL_LOCATION, raise_if_not_found=False)
        quants = self.env["stock.quant"].search([
            ("product_id", "=", self.id),
            ("company_id", "=", self.env.company.id),
            ("owner_id", "=", False),
            "|", ("location_id.usage", "=", "internal"),
            ("location_id", "=", rental.id if rental else False),
        ])
        return sum(quants.mapped("quantity"))

    def mgs_rental_available(self, date_from, date_to, ignore_event=None):
        """Unidades libres para alquilar entre esas dos fechas, ambas incluidas.

        Un arco reservado el 12 de junio no puede prometerse a otro evento ese
        día, aunque hoy esté en la estantería."""
        self.ensure_one()
        if not date_from or not date_to:
            raise UserError(_("Indica las fechas del evento."))
        if date_to < date_from:
            raise UserError(_("La fecha de devolución no puede ser anterior a la del evento."))
        domain = [
            ("product_id", "=", self.id),
            ("is_rental", "=", True),
            ("event_id.state", "in", ("confirmed", "delivered")),
            ("event_id.company_id", "=", self.env.company.id),
            # Dos rangos se solapan si cada uno empieza antes de que acabe el otro.
            ("event_id.event_date", "<=", date_to),
            ("event_id.return_date", ">=", date_from),
        ]
        if ignore_event:
            domain.append(("event_id", "!=", ignore_event.id))
        booked = sum(self.env["mgs.event.line"].search(domain).mapped("quantity"))
        return self.mgs_rental_fleet() - booked


class MgsEvent(models.Model):
    _name = "mgs.event"
    _description = "Evento o encargo"
    _order = "event_date desc, id desc"

    name = fields.Char("Referencia", default="Nuevo", readonly=True, copy=False)
    partner_id = fields.Many2one("res.partner", "Cliente", required=True)
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company,
                                 required=True, readonly=True)
    event_date = fields.Date("Fecha del evento", required=True)
    return_date = fields.Date(
        "Devolución prevista del material", required=True,
        help="Hasta cuándo está comprometido el material de alquiler. "
             "Mientras tanto no se puede prometer a otro evento.")
    state = fields.Selection([
        ("draft", "Presupuesto"), ("confirmed", "Aceptado"),
        ("delivered", "Entregado"), ("returned", "Material devuelto"),
        ("done", "Cobrado"), ("cancelled", "Cancelado"),
    ], default="draft", readonly=True, string="Estado")
    line_ids = fields.One2many("mgs.event.line", "event_id", "Partidas")
    payment_ids = fields.One2many("mgs.event.payment", "event_id", "Cobros", readonly=True)
    note = fields.Text("Notas del encargo")

    amount_total = fields.Float("Total", compute="_compute_amounts", store=True)
    amount_deposit = fields.Float("Fianza del material", compute="_compute_amounts", store=True)
    amount_paid = fields.Float("Cobrado", compute="_compute_amounts", store=True)
    amount_due = fields.Float("Pendiente", compute="_compute_amounts", store=True)

    confirmed_at = fields.Datetime(readonly=True)
    delivered_at = fields.Datetime(readonly=True)
    returned_at = fields.Datetime(readonly=True)
    move_ids = fields.One2many("stock.move", "mgs_event_id", "Movimientos", readonly=True)
    pending_return = fields.Boolean("Queda material sin devolver",
                                    compute="_compute_amounts", store=True)

    # Cobro en caja: las partidas que se venden (flores, ramos) pueden llevarse
    # al TPV como un pedido listo para cobrar. El alquiler y la fianza no: se
    # quedan aquí, con «Registrar cobro». Ver action_mgs_checkout_pos y
    # pos_event_checkout.js.
    mgs_pos_charged = fields.Boolean(
        "Vendido en caja", compute="_compute_mgs_pos_charged",
        help="Alguna venta de caja ya ha cobrado las partidas de este encargo.")
    mgs_pos_chargeable = fields.Boolean(
        "Se puede cobrar en caja", compute="_compute_mgs_pos_charged")

    def _compute_mgs_pos_charged(self):
        Order = self.env["pos.order"].sudo()
        for event in self:
            charged = isinstance(event.id, int) and bool(Order.search_count([
                ("mgs_event_ref", "=", event.id),
                ("state", "in", ("paid", "done", "invoiced")),
            ]))
            has_sellable = any(
                not line.is_rental and float_compare(
                    line.delivered_qty, line.quantity,
                    precision_rounding=line.product_id.uom_id.rounding or 0.01) < 0
                for line in event.line_ids)
            event.mgs_pos_charged = charged
            event.mgs_pos_chargeable = (
                event.state in ("draft", "confirmed") and has_sellable)

    @api.depends("line_ids.subtotal", "line_ids.quantity", "line_ids.is_rental",
                 "line_ids.delivered_qty", "line_ids.returned_qty", "line_ids.damaged_qty",
                 "payment_ids.amount")
    def _compute_amounts(self):
        for event in self:
            event.amount_total = sum(event.line_ids.mapped("subtotal"))
            event.amount_deposit = sum(
                line.quantity * line.product_id.mgs_rental_deposit
                for line in event.line_ids if line.is_rental)
            event.amount_paid = sum(event.payment_ids.mapped("amount"))
            event.amount_due = event.amount_total - event.amount_paid
            event.pending_return = any(
                line.is_rental and float_compare(
                    line.delivered_qty, line.returned_qty + line.damaged_qty,
                    precision_rounding=line.product_id.uom_id.rounding or 0.01) > 0
                for line in event.line_ids)

    # ------------------------------------------------------------------
    # Permisos y candados
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            forbidden = set(vals) - {"partner_id", "event_date", "return_date",
                                     "line_ids", "note"}
            if forbidden:
                raise AccessError(_("El estado y los cobros los establece el servidor."))
            vals["name"] = self.env["ir.sequence"].next_by_code("mgs.event") or "Nuevo"
            vals["company_id"] = self.env.company.id
        return super().create(vals_list)

    # Lo único que se puede anotar en un evento ya entregado: cuántas unidades
    # vuelven y en qué estado.
    RETURN_FIELDS = {"return_ok_qty", "return_damaged_qty"}

    def write(self, vals):
        require_manager(self.env)
        if set(vals) - {"partner_id", "event_date", "return_date", "line_ids", "note"}:
            raise AccessError(_("El estado y los cobros los establece el servidor."))
        # Anotar la devolución llega por aquí, no por la línea: el formulario
        # guarda el evento entero con un comando sobre `line_ids`. Se admite
        # solo si toca exclusivamente las casillas de devolución de líneas que
        # ya existen; cualquier otra cosa sigue vetada tras aceptar.
        if set(vals) == {"line_ids"}:
            annotating = all(
                len(command) == 3 and command[0] == 1
                and not (set(command[2]) - self.RETURN_FIELDS)
                for command in vals["line_ids"])
            if annotating and all(event.state in ("delivered", "returned") for event in self):
                for event in self:
                    if any(command[1] not in event.line_ids.ids
                           for command in vals["line_ids"]):
                        raise AccessError(_("Esa partida no es de este evento."))
                return super().write(vals)
        for event in self:
            if event.state != "draft":
                raise UserError(_("Solo se edita un presupuesto sin aceptar. "
                                  "Un evento aceptado se corrige cancelándolo."))
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        if any(event.state != "draft" for event in self):
            raise UserError(_("Los eventos aceptados se conservan para trazabilidad; "
                              "cancélalos en vez de borrarlos."))
        return super().unlink()

    def _lock(self):
        require_manager(self.env)
        self.ensure_one()
        self.check_access("write")
        if self.company_id != self.env.company:
            raise UserError(_("El evento no es de esta tienda."))
        self.env.cr.execute("SELECT id FROM mgs_event WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset()

    def _lock_products(self):
        """Serializa la comprobación de disponibilidad con recepción y apertura.

        Sin este candado, dos eventos confirmados a la vez podrían prometer el
        mismo arco: las dos verían la misma disponibilidad antes de que ninguna
        hubiera guardado su reserva."""
        products = self.line_ids.product_id
        if products:
            self.env.cr.execute(
                "SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE",
                [tuple(products.ids)])

    def _check_dates(self):
        if not self.event_date or not self.return_date:
            raise UserError(_("Indica la fecha del evento y la de devolución."))
        if self.return_date < self.event_date:
            raise UserError(_("La devolución no puede ser anterior al evento."))

    # ------------------------------------------------------------------
    # Recorrido
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Presupuesto aceptado: el material queda comprometido, no sale aún."""
        self._lock()
        if self.state == "confirmed":
            return True
        if self.state != "draft":
            raise UserError(_("Este evento ya ha pasado de presupuesto."))
        if not self.line_ids:
            raise UserError(_("Añade al menos una partida al presupuesto."))
        self._check_dates()
        self._lock_products()
        for line in self.line_ids:
            line._check_valid()
            if line.is_rental:
                free = line.product_id.mgs_rental_available(
                    self.event_date, self.return_date, ignore_event=self)
                if float_compare(free, line.quantity,
                                 precision_rounding=line.product_id.uom_id.rounding) < 0:
                    raise UserError(_(
                        "De «%(producto)s» solo quedan %(libres)g libres entre el "
                        "%(desde)s y el %(hasta)s, y hacen falta %(piden)g. "
                        "Ya hay otro evento con ese material esas fechas.",
                        producto=line.product_id.display_name, libres=free,
                        desde=self.event_date, hasta=self.return_date,
                        piden=line.quantity))
        super().write({"state": "confirmed", "confirmed_at": fields.Datetime.now()})
        return True

    def action_deliver(self):
        """Sale el material: la venta se va al cliente, el alquiler a tránsito."""
        self._lock()
        if self.state == "delivered":
            return True
        if self.state != "confirmed":
            raise UserError(_("Solo se entrega un evento aceptado."))
        self._lock_products()
        rental_location = self.env.ref(RENTAL_LOCATION)
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1)
        if not warehouse:
            raise UserError(_("No hay almacén configurado en esta tienda."))
        source = warehouse.lot_stock_id
        customers = self.env.ref("stock.stock_location_customers")
        for line in self.line_ids:
            # Una partida vendida ya en caja sale con la venta del TPV; aquí no
            # se vuelve a mover (si no, se descontaría el stock dos veces).
            if float_compare(line.delivered_qty, line.quantity,
                             precision_rounding=line.product_id.uom_id.rounding or 0.01) >= 0:
                continue
            line._check_valid()
            if line.product_id.mgs_is_composition:
                # Siempre se vende, nunca se alquila (ver _mgs_deliver_composition).
                line._mgs_deliver_composition(source, customers)
                super(MgsEventLine, line).write({"delivered_qty": line.quantity})
                continue
            if not line.product_id.is_storable:
                # Lo unico no almacenable que puede llegar aqui, aparte de una
                # composicion (ya tratada arriba), es un servicio de verdad
                # (montaje, transporte...), que no tiene nada que sacar del
                # almacen. Ver "0.2".
                continue
            destination = rental_location if line.is_rental else customers
            move = self.env["stock.move"].create({
                "name": "%s - %s" % (self.name, line.product_id.display_name),
                "product_id": line.product_id.id,
                "product_uom": line.product_id.uom_id.id,
                "product_uom_qty": line.quantity,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
                "mgs_event_id": self.id,
                "mgs_event_line_id": line.id,
            })
            move._action_confirm(merge=False)
            # Misma asignación por caducidad y antigüedad que usa el TPV.
            move._mgs_reserve_available_lots()
            move.picked = True
            move._action_done()
            super(MgsEventLine, line).write({"delivered_qty": line.quantity})
        super().write({"state": "delivered", "delivered_at": fields.Datetime.now()})
        return True

    def action_register_return(self):
        """Vuelve el material: lo entero al almacén, lo roto a mermas."""
        self._lock()
        if self.state not in ("delivered", "returned"):
            raise UserError(_("Todavía no se ha entregado nada de este evento."))
        rental_location = self.env.ref(RENTAL_LOCATION)
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1)
        destination = warehouse.lot_stock_id
        moved = False
        for line in self.line_ids.filtered("is_rental"):
            pending_ok = line.return_ok_qty
            pending_broken = line.return_damaged_qty
            rounding = line.product_id.uom_id.rounding
            if float_is_zero(pending_ok, precision_rounding=rounding) and \
               float_is_zero(pending_broken, precision_rounding=rounding):
                continue
            if pending_ok < 0 or pending_broken < 0:
                raise UserError(_("Las cantidades devueltas no pueden ser negativas."))
            outstanding = line.delivered_qty - line.returned_qty - line.damaged_qty
            if float_compare(pending_ok + pending_broken, outstanding,
                             precision_rounding=rounding) > 0:
                raise UserError(_(
                    "De «%(producto)s» solo quedan %(fuera)g unidades fuera; no se "
                    "pueden devolver %(total)g.", producto=line.product_id.display_name,
                    fuera=outstanding, total=pending_ok + pending_broken))
            moved = True
            returning = pending_ok + pending_broken
            move = self.env["stock.move"].create({
                "name": _("Devolución %s - %s") % (self.name, line.product_id.display_name),
                "product_id": line.product_id.id,
                "product_uom": line.product_id.uom_id.id,
                "product_uom_qty": returning,
                "location_id": rental_location.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
                "mgs_event_id": self.id,
                "mgs_event_line_id": line.id,
            })
            move._action_confirm(merge=False)
            move._mgs_return_from_rental(line)
            move.picked = True
            move._action_done()
            # Lo que vuelve roto se da de baja acto seguido, con su coste real.
            if not float_is_zero(pending_broken, precision_rounding=rounding):
                line._scrap_damaged(pending_broken, move, destination)
            super(MgsEventLine, line).write({
                "returned_qty": line.returned_qty + pending_ok,
                "damaged_qty": line.damaged_qty + pending_broken,
                "return_ok_qty": 0.0, "return_damaged_qty": 0.0,
            })
        if not moved:
            raise UserError(_("Indica cuántas unidades vuelven enteras y cuántas rotas."))
        super().write({"state": "returned", "returned_at": fields.Datetime.now()})
        return True

    def action_register_payment(self, amount, method="cash", note=False):
        """Señal o cobro final. El dinero de un evento no pasa por el TPV."""
        self._lock()
        if self.state in ("draft", "cancelled"):
            raise UserError(_("Acepta el presupuesto antes de cobrar la señal."))
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount <= 0:
            raise UserError(_("El importe cobrado tiene que ser positivo."))
        if float_compare(amount, self.amount_due, precision_rounding=0.01) > 0:
            raise UserError(_("El cobro supera lo que queda pendiente (%.2f).", self.amount_due))
        self.env["mgs.event.payment"].sudo().create({
            "event_id": self.id, "amount": amount, "method": method,
            "note": note or False, "user_id": self.env.uid,
        })
        return True

    # ------------------------------------------------------------------
    # Cobro en caja
    # ------------------------------------------------------------------
    def action_mgs_checkout_pos(self):
        """Abre el selector de partidas que se van a cobrar en el TPV."""
        require_manager(self.env)
        self.ensure_one()
        if not self.mgs_pos_chargeable:
            raise UserError(_(
                "Este encargo no se puede cobrar en caja: o no tiene nada que "
                "vender (todo es alquiler o ya se entregó), o no está en "
                "presupuesto/aceptado."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "mgs.event.pos.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_event_id": self.id},
        }

    @api.model
    def mgs_pos_load_event(self, event_id, selected_lines=None):
        """Datos del encargo para que el TPV monte el pedido (lo llama
        pos_event_checkout.js al arrancar)."""
        if not (self.env.su or self.env.user.has_group("mi_gestor_stock.group_mgs_user")
                or self.env.user.has_group("mi_gestor_stock.group_mgs_manager")):
            raise AccessError(_("No tienes permiso para cobrar encargos en caja."))
        event = self.sudo().browse(int(event_id)).exists()
        if not event or event.company_id != self.env.company:
            return {"error": _("El encargo ya no está disponible.")}
        if not event.mgs_pos_chargeable:
            return {"error": _("El encargo %s ya no se puede cobrar en caja.") % event.name}
        selected = {int(item["line_id"]): float(item["qty"])
                    for item in (selected_lines or [])
                    if item.get("line_id") and item.get("qty")}
        # Mantiene operativos enlaces de caja ya abiertos antes de esta mejora.
        if not selected:
            selected = {line.id: line.quantity - line.delivered_qty
                        for line in event.line_ids if not line.is_rental}
        lines = []
        for line in event.line_ids.filtered(lambda item: not item.is_rental and item.id in selected):
            qty = selected[line.id]
            remaining = line.quantity - line.delivered_qty
            if qty <= 0 or float_compare(qty, remaining,
                                         precision_rounding=line.product_id.uom_id.rounding or 0.01) > 0:
                return {"error": _("La cantidad elegida para «%s» ya no está disponible.") % line.product_id.display_name}
            line._check_valid()
            if not line.product_id.available_in_pos:
                return {"error": _("«%s» no está disponible en el TPV.") % line.product_id.display_name}
            entry = {
                "event_line_id": line.id,
                "product_id": line.product_id.id,
                "qty": qty,
                # El presupuesto va con impuestos incluidos (lo que paga el
                # cliente). El TPV suma el IVA sobre el precio que le pasamos,
                # así que hay que darle el neto para que el total del ticket
                # coincida con el del presupuesto.
                "price_unit": event._mgs_pos_price_unit(line),
            }
            if line.product_id.mgs_is_composition:
                entry["bouquet_spec"] = json.dumps([
                    {"product_id": component.product_id.id, "qty": component.quantity}
                    for component in line.component_ids])
            lines.append(entry)
        return {
            "event_id": event.id,
            "name": event.name,
            "partner_id": event.partner_id.id,
            "lines": lines,
        }

    def _mgs_pos_price_unit(self, line):
        """Precio unitario SIN impuestos para el TPV, de forma que el importe
        con IVA del ticket sea igual al del presupuesto (`quantity * unit_price`,
        que se entiende con impuestos incluidos)."""
        self.ensure_one()
        product = line.product_id
        taxes = product.taxes_id.filtered(
            lambda tax: not tax.company_id or tax.company_id == self.company_id)
        if not taxes or not line.unit_price:
            return line.unit_price
        if all(tax.price_include for tax in taxes):
            # El TPV ya trata el precio como con impuestos incluidos.
            return line.unit_price
        result = taxes.compute_all(
            1.0, currency=self.company_id.currency_id, quantity=1.0, product=product)
        included = result.get("total_included") or 1.0
        excluded = result.get("total_excluded") or 1.0
        return line.unit_price * (excluded / included)

    @api.model
    def mgs_pos_link_order(self, event_id, order_uuid, selected_lines=None):
        """El TPV enlaza el pedido con el encargo (lo llama nada más montarlo, y
        otra vez al cobrarlo). Deja `mgs_event_ref` en el pedido —así el enlace
        sobrevive aunque falle el aviso posterior— y, si el pedido ya está
        cobrado, liquida el encargo. Idempotente; hay una segunda red en
        pos.order._process_order."""
        if not (self.env.su or self.env.user.has_group("mi_gestor_stock.group_mgs_user")
                or self.env.user.has_group("mi_gestor_stock.group_mgs_manager")):
            raise AccessError(_("No tienes permiso para cobrar encargos en caja."))
        order = self.env["pos.order"].sudo().search(
            [("uuid", "=", order_uuid)], limit=1)
        event = self.sudo().browse(int(event_id)).exists()
        if not order or not event or order.company_id != event.company_id:
            return False
        if order.mgs_event_ref != event.id:
            order.write({"mgs_event_ref": event.id})
        if order.state in ("paid", "done", "invoiced"):
            order._mgs_settle_event(selected_lines)
        return True

    def _mgs_force_done(self):
        """Cierra el encargo cuando la venta de caja lo deja pagado y entregado.
        Solo servidor: lo llama la liquidación del pedido de caja."""
        self.ensure_one()
        if not self.env.su:
            raise AccessError(_("El estado del encargo lo cierra el servidor."))
        super().write({"state": "done"})

    def action_done(self):
        self._lock()
        if self.state == "done":
            return True
        if self.state not in ("delivered", "returned"):
            raise UserError(_("Entrega el evento antes de cerrarlo."))
        if not float_is_zero(self.amount_due, precision_rounding=0.01):
            raise UserError(_("Quedan %.2f € por cobrar.", self.amount_due))
        if self.pending_return:
            raise UserError(_("Queda material de alquiler sin devolver. Regístralo "
                              "como devuelto o como roto antes de cerrar el evento."))
        super().write({"state": "done"})
        return True

    def action_cancel(self):
        self._lock()
        if self.state == "cancelled":
            return True
        if self.state in ("delivered", "returned", "done"):
            raise UserError(_("Ya ha salido material: registra la devolución en vez "
                              "de cancelar."))
        super().write({"state": "cancelled"})
        return True

    def action_draft(self):
        self._lock()
        if self.state != "cancelled":
            raise UserError(_("Solo se reabre un evento cancelado."))
        super().write({"state": "draft", "confirmed_at": False})
        return True


class MgsEventLine(models.Model):
    _name = "mgs.event.line"
    _description = "Partida de un evento o encargo"

    event_id = fields.Many2one("mgs.event", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="event_id.company_id", store=True)
    product_id = fields.Many2one(
        "product.product", "Producto", required=True,
        help="Si es una composición a medida (ramo, centro de mesa...), indica "
             "también de qué flores y material está hecha: el evento descuenta "
             "cada una de su partida, no la composición en sí, que no tiene "
             "existencias propias.")
    # Solo tiene sentido -y solo se acepta- cuando product_id es una composición
    # a medida (ver _check_mgs_composition_components). Se escribe en la propia
    # línea, sin catálogo de recetas: cada evento monta el ramo que lleva.
    component_ids = fields.One2many(
        "mgs.event.line.component", "line_id", string="Materiales")
    # Related solo para que la vista pueda mostrar/ocultar «Materiales» según el
    # producto elegido: un domain de vista no puede mirar un subcampo de un
    # many2one que no esté ya cargado en el formulario.
    product_is_composition = fields.Boolean(related="product_id.mgs_is_composition")
    is_rental = fields.Boolean("Se alquila")
    quantity = fields.Float("Cantidad", default=1.0, required=True)
    unit_price = fields.Float("Precio unitario", digits="Product Price")
    subtotal = fields.Float(compute="_compute_subtotal", store=True, string="Importe")

    delivered_qty = fields.Float("Entregado", readonly=True)
    returned_qty = fields.Float("Devuelto entero", readonly=True)
    damaged_qty = fields.Float("Devuelto roto", readonly=True)
    # Casillas de trabajo: lo que la dueña anota antes de pulsar «Registrar
    # devolución». Se vacían al aplicarla.
    return_ok_qty = fields.Float("Vuelven enteras")
    return_damaged_qty = fields.Float("Vuelven rotas")

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.is_rental = line.product_id.mgs_rental_ok
                line.unit_price = line.product_id.list_price

    @api.constrains("product_id", "component_ids")
    def _check_mgs_composition_components(self):
        # Una composicion no tiene existencias propias (is_storable=False,
        # forzado en mgs_bouquet.py): sin materiales, action_deliver() no
        # sabria que flor descontar y se saltaria la linea en silencio (ver
        # la seccion "0.2" del traspaso). Con esto no puede entrar sin ellos,
        # y ademas se validan contra el MISMO parser que usa el cobro del TPV.
        PosLine = self.env["pos.order.line"]
        for line in self:
            if line.product_id.mgs_is_composition:
                if not line.component_ids:
                    raise UserError(_(
                        "«%s» es una composición a medida: indica de qué "
                        "flores y material está hecha.",
                        line.product_id.display_name))
                spec = json.dumps([
                    {"product_id": component.product_id.id,
                     "qty": component.quantity}
                    for component in line.component_ids])
                PosLine._mgs_parse_components(spec)
            elif line.component_ids:
                raise UserError(_(
                    "«%s» no es una composición a medida: no lleva materiales.",
                    line.product_id.display_name))

    def _check_valid(self):
        self.ensure_one()
        if not math.isfinite(self.quantity) or self.quantity <= 0:
            raise UserError(_("Las cantidades del presupuesto tienen que ser positivas."))
        if not math.isfinite(self.unit_price) or self.unit_price < 0:
            raise UserError(_("Los precios no pueden ser negativos."))
        if self.is_rental and not self.product_id.mgs_rental_ok:
            raise UserError(_("«%s» no está marcado como artículo de alquiler.",
                              self.product_id.display_name))
        if self.is_rental and not self.product_id.is_storable:
            raise UserError(_("«%s» no lleva control de existencias: no se puede alquilar.",
                              self.product_id.display_name))
        # Sin "else raise" para el resto de composiciones: una composición con
        # materiales es válida (_check_mgs_composition_components ya lo exige al
        # guardar la línea), y action_deliver() sabe expandirla.

    def _mgs_deliver_composition(self, source, destination):
        """Entrega una composición (ramo, centro...) de un evento: un
        movimiento por MATERIAL de la línea, multiplicado por la cantidad de
        la línea. Mismo patrón que
        mgs_bouquet.StockPicking._create_move_from_pos_order_lines, pero para
        movimientos sueltos en vez de para una línea del TPV. Una composición
        nunca es de alquiler (is_storable=False lo impide en _check_valid),
        así que siempre entrega vendiendo, nunca a tránsito."""
        self.ensure_one()
        for component in self.component_ids:
            move = self.env["stock.move"].create({
                "name": "%s - %s" % (self.event_id.name, component.product_id.display_name),
                "product_id": component.product_id.id,
                "product_uom": component.product_id.uom_id.id,
                "product_uom_qty": component.quantity * self.quantity,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
                "mgs_event_id": self.event_id.id,
                "mgs_event_line_id": self.id,
            })
            move._action_confirm(merge=False)
            move._mgs_reserve_available_lots()
            move.picked = True
            move._action_done()

    def _scrap_damaged(self, quantity, move, location):
        """Baja del material que ha vuelto roto, con su partida y coste real."""
        self.ensure_one()
        lots = move.move_line_ids.filtered(lambda ml: ml.lot_id)
        scrap_values = {
            "product_id": self.product_id.id,
            "scrap_qty": quantity,
            "product_uom_id": self.product_id.uom_id.id,
            "location_id": location.id,
            "company_id": self.company_id.id,
            "mgs_reason": "breakage",
        }
        if lots:
            scrap_values["lot_id"] = lots[0].lot_id.id
        scrap = self.env["stock.scrap"].create(scrap_values)
        scrap.do_scrap()
        return scrap

    def write(self, vals):
        if not self.env.su:
            require_manager(self.env)
            protected = {"delivered_qty", "returned_qty", "damaged_qty"}
            if protected.intersection(vals):
                raise AccessError(_("Las cantidades entregadas y devueltas las "
                                    "registra el servidor."))
            for line in self:
                if line.event_id.state not in ("draft", "delivered", "returned"):
                    raise UserError(_("No se edita una partida de un evento cerrado."))
                if (line.event_id.state in ("delivered", "returned")
                        and set(vals) - {"return_ok_qty", "return_damaged_qty"}):
                    raise UserError(_("Después de entregar solo se anota la devolución."))
        return super().write(vals)

    def unlink(self):
        if not self.env.su and any(line.event_id.state != "draft" for line in self):
            raise UserError(_("Las partidas de un evento aceptado se conservan."))
        return super().unlink()


class MgsEventLineComponent(models.Model):
    """Material de una composición a medida de un evento (una flor, un follaje,
    un envoltorio) con la cantidad que lleva UNA unidad de la composición.
    Se valida contra el mismo parser que el cobro del TPV, en
    mgs.event.line._check_mgs_composition_components."""
    _name = "mgs.event.line.component"
    _description = "Material de una composición a medida de un evento"

    line_id = fields.Many2one("mgs.event.line", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="line_id.company_id", store=True)
    product_id = fields.Many2one("product.product", "Material", required=True)
    quantity = fields.Float("Cantidad", default=1.0, required=True)


class MgsEventPayment(models.Model):
    _name = "mgs.event.payment"
    _description = "Cobro de un evento o encargo"
    _order = "id"

    event_id = fields.Many2one("mgs.event", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="event_id.company_id", store=True)
    amount = fields.Float("Importe", required=True, digits="Product Price")
    method = fields.Selection([("cash", "Efectivo"), ("card", "Tarjeta"),
                               ("transfer", "Transferencia")],
                              default="cash", required=True, string="Forma de pago")
    date = fields.Datetime("Fecha", default=fields.Datetime.now, readonly=True)
    user_id = fields.Many2one("res.users", "Registrado por", readonly=True)
    note = fields.Char("Concepto")
    pos_order_id = fields.Many2one("pos.order", "Pedido TPV", readonly=True,
                                   copy=False, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Los cobros se registran desde el evento."))
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_("Un cobro registrado no se modifica; registra otro."))

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Un cobro registrado se conserva."))
        return super().unlink()


class StockMove(models.Model):
    _inherit = "stock.move"

    mgs_event_id = fields.Many2one("mgs.event", readonly=True, copy=False, index=True)
    mgs_event_line_id = fields.Many2one("mgs.event.line", readonly=True, copy=False)

    def write(self, vals):
        if {"mgs_event_id", "mgs_event_line_id"}.intersection(vals):
            raise AccessError(_("No se cambia el origen de un movimiento de evento."))
        return super().write(vals)

    def _mgs_return_from_rental(self, line):
        """Devuelve exactamente las partidas que salieron a ese evento."""
        self.ensure_one()
        self.move_line_ids.unlink()
        sources = line.event_id.move_ids.filtered(
            lambda move: move.mgs_event_line_id == line and move.state == "done"
            and move.location_dest_id == self.location_id).move_line_ids
        remaining = self.product_uom_qty
        for source in sources.sorted("id"):
            returned = self.env["stock.move.line"].search([
                ("mgs_return_origin_id", "=", source.id), ("state", "!=", "cancel"),
            ])
            available = source.quantity_product_uom - sum(returned.mapped("quantity_product_uom"))
            quantity = min(remaining, max(0, available))
            if quantity <= 0:
                continue
            self.env["stock.move.line"].create({
                "move_id": self.id, "product_id": self.product_id.id,
                "product_uom_id": self.product_id.uom_id.id,
                "location_id": self.location_id.id,
                "location_dest_id": self.location_dest_id.id,
                "lot_id": source.lot_id.id, "quantity": quantity,
                "mgs_return_origin_id": source.id,
            })
            remaining -= quantity
        if not float_is_zero(remaining, precision_rounding=self.product_id.uom_id.rounding):
            raise UserError(_("Se están devolviendo más unidades de las que salieron."))


class MgsEventPaymentWizard(models.TransientModel):
    """Cobrar la señal o el resto sin poder tocar nada más del evento."""
    _name = "mgs.event.payment.wizard"
    _description = "Registrar cobro de un evento"

    event_id = fields.Many2one("mgs.event", "Evento", required=True)
    amount_due = fields.Float(related="event_id.amount_due", string="Pendiente")
    amount = fields.Float("Importe cobrado", required=True, digits="Product Price")
    method = fields.Selection([("cash", "Efectivo"), ("card", "Tarjeta"),
                               ("transfer", "Transferencia")],
                              default="cash", required=True, string="Forma de pago")
    note = fields.Char("Concepto")

    def action_apply(self):
        require_manager(self.env)
        self.ensure_one()
        self.event_id.action_register_payment(self.amount, self.method, self.note)
        return {"type": "ir.actions.act_window_close"}


class MgsEventPosWizard(models.TransientModel):
    """Selección temporal: no abre la edición de las partidas del encargo."""
    _name = "mgs.event.pos.wizard"
    _description = "Partidas del encargo para cobrar en caja"

    event_id = fields.Many2one("mgs.event", "Encargo", required=True, readonly=True)
    line_ids = fields.One2many("mgs.event.pos.wizard.line", "wizard_id", "Partidas")

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        event = self.env["mgs.event"].browse(values.get("event_id") or self.env.context.get("default_event_id")).exists()
        if event:
            values["event_id"] = event.id
            values["line_ids"] = [(0, 0, {
                "event_line_id": line.id,
                "quantity": line.quantity - line.delivered_qty,
            }) for line in event.line_ids if not line.is_rental and float_compare(
                line.delivered_qty, line.quantity,
                precision_rounding=line.product_id.uom_id.rounding or 0.01) < 0]
        return values

    def action_open_pos(self):
        require_manager(self.env)
        self.ensure_one()
        if not self.event_id.mgs_pos_chargeable:
            raise UserError(_("Este encargo ya no tiene partidas disponibles para cobrar en caja."))
        selected = []
        for item in self.line_ids:
            line = item.event_line_id
            remaining = line.quantity - line.delivered_qty
            if item.quantity <= 0:
                continue
            if float_compare(item.quantity, remaining,
                             precision_rounding=line.product_id.uom_id.rounding or 0.01) > 0:
                raise UserError(_("De «%s» solo quedan %g unidades para cobrar en caja.") %
                                (line.product_id.display_name, remaining))
            line._check_valid()
            if not line.product_id.available_in_pos:
                raise UserError(_("«%s» no está disponible en el TPV.") % line.product_id.display_name)
            selected.append({"line_id": line.id, "qty": item.quantity})
        if not selected:
            raise UserError(_("Elige al menos una cantidad mayor que cero."))
        config = self.env["pos.config"].sudo().search(
            [("company_id", "=", self.event_id.company_id.id)], limit=1)
        if not config:
            raise UserError(_("No hay ninguna caja configurada. Entra una vez en «Vender»."))
        return {"type": "ir.actions.act_url",
                "url": "/pos/ui?" + urlencode({"config_id": config.id,
                                                   "mgs_event": self.event_id.id,
                                                   "mgs_lines": json.dumps(selected)}),
                "target": "self"}


class MgsEventPosWizardLine(models.TransientModel):
    _name = "mgs.event.pos.wizard.line"
    _description = "Partida seleccionada para cobrar en caja"

    wizard_id = fields.Many2one("mgs.event.pos.wizard", required=True, ondelete="cascade")
    event_line_id = fields.Many2one("mgs.event.line", "Partida", required=True, readonly=True)
    product_id = fields.Many2one(related="event_line_id.product_id", string="Producto", readonly=True)
    available_qty = fields.Float(related="event_line_id.quantity", string="Presupuestado", readonly=True)
    delivered_qty = fields.Float(related="event_line_id.delivered_qty", string="Ya cobrado", readonly=True)
    quantity = fields.Float("Cantidad a cobrar", required=True, digits="Product Unit of Measure")


class PosOrder(models.Model):
    """Enlace de una venta de caja con el encargo que la originó.

    Cuando un encargo se cobra desde «Vender» (botón «Cobrar en caja» →
    pos_event_checkout.js), el pedido del TPV lleva `mgs_event_ref`. Al cobrarlo,
    el servidor marca esas partidas como entregadas —el stock ya lo ha movido el
    propio TPV— y anota el cobro en el encargo. Si con eso queda pagado y no hay
    alquiler pendiente, lo cierra."""
    _inherit = "pos.order"

    # pos.order sincroniza todos sus campos al TPV (no tiene lista propia en
    # _load_pos_data_fields), así que este entero viaja solo, de ida y de vuelta.
    mgs_event_ref = fields.Integer(
        "Encargo de origen", readonly=True, copy=False, index=True)

    @api.model
    def _process_order(self, order, existing_order):
        order_id = super()._process_order(order, existing_order)
        record = self.browse(order_id)
        if record.mgs_event_ref and record.state in ("paid", "done", "invoiced"):
            record.sudo()._mgs_settle_event()
        return order_id

    def _mgs_event_payment_note(self):
        self.ensure_one()
        return _("Cobrado en caja · %s") % (self.pos_reference or self.name or self.id)

    def _mgs_event_payment_method(self):
        self.ensure_one()
        methods = self.payment_ids.mapped("payment_method_id")
        if methods and all(method.is_cash_count for method in methods):
            return "cash"
        return "card"

    def _mgs_settle_event(self, selected_lines=None):
        self.ensure_one()
        event = self.env["mgs.event"].sudo().browse(self.mgs_event_ref).exists()
        if not event or event.state in ("done", "cancelled"):
            return
        if self.env["mgs.event.payment"].sudo().search_count([("pos_order_id", "=", self.id)]):
            return
        selected = {int(item["line_id"]): float(item["qty"])
                    for item in (selected_lines or []) if item.get("line_id") and item.get("qty")}
        # Red de seguridad para pedidos antiguos que llegaron ya enlazados.
        if not selected:
            selected = {line.id: line.quantity - line.delivered_qty
                        for line in event.line_ids if not line.is_rental}
        sellable = event.line_ids.filtered(lambda line: line.id in selected and not line.is_rental)
        if not sellable or len(sellable) != len(selected):
            return
        rounding = lambda line: line.product_id.uom_id.rounding or 0.01
        # La selección se entrega al TPV antes de pagar. Si allí se cambia una
        # cantidad, no marcamos el encargo como entregado con datos antiguos.
        selected_by_product = {}
        for line in sellable:
            selected_by_product[line.product_id.id] = selected_by_product.get(line.product_id.id, 0.0) + selected[line.id]
        ordered_by_product = {}
        for order_line in self.lines:
            ordered_by_product[order_line.product_id.id] = ordered_by_product.get(order_line.product_id.id, 0.0) + order_line.qty
        if any(float_compare(ordered_by_product.get(product_id, 0.0), quantity,
                             precision_rounding=self.env["product.product"].browse(product_id).uom_id.rounding or 0.01) != 0
               for product_id, quantity in selected_by_product.items()):
            return
        for line in sellable:
            qty = selected[line.id]
            remaining = line.quantity - line.delivered_qty
            if qty <= 0 or float_compare(qty, remaining, precision_rounding=rounding(line)) > 0:
                return
            line.sudo().write({"delivered_qty": line.delivered_qty + qty})
        # Lo que valen esas partidas según el presupuesto. Si el TPV ha cobrado
        # esa cifra salvo redondeo (el neto por unidad no siempre divide justo),
        # se anota el importe del presupuesto para que el encargo cuadre; si hay
        # una diferencia real (un descuento en caja), se anota lo cobrado y el
        # encargo queda pendiente para que la responsable lo revise.
        expected = sum(line.unit_price * selected[line.id] for line in sellable)
        amount = self.amount_paid
        if abs(amount - expected) <= max(0.05, 0.01 * len(sellable)):
            amount = expected
        self.env["mgs.event.payment"].sudo().create({
            "event_id": event.id,
            "amount": amount,
            "method": self._mgs_event_payment_method(),
            "note": self._mgs_event_payment_note(),
            "user_id": (self.user_id or self.env.user).id,
            "pos_order_id": self.id,
        })
        event.invalidate_recordset()
        if (float_is_zero(event.amount_due, precision_rounding=0.01)
                and not event.pending_return
                and not any(line.is_rental for line in event.line_ids)
                and event.state in ("draft", "confirmed")):
            event._mgs_force_done()
