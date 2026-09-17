# -*- coding: utf-8 -*-
"""Correcciones trazables: cómo se arregla un error sin borrar una venta.

Una venta confirmada no se borra nunca. Cuando hay un error se resuelve con
una operación NUEVA, y aquí se guarda el por qué:

* **Producto, cantidad o importe mal** → se hace la devolución por el camino
  de siempre (pantalla de devoluciones del TPV, que ya mueve el stock y el
  dinero bien) y, si hace falta, la venta correcta. Este registro solo
  ENLAZA esas operaciones con su motivo. A propósito no las crea: duplicar
  aquí el motor de devoluciones de Odoo sería reimplementar —peor— algo que
  ya está probado, y es lo que garantiza que el stock salga siempre de
  operaciones comerciales reales.

* **Método de pago equivocado** → el cobro original NO se toca. Se anota la
  reclasificación al método correcto y, si la caja sigue abierta y el cambio
  entra o sale de efectivo, se ajusta el efectivo esperado con el mecanismo
  del propio TPV (`pos.session.try_cash_in_out`, que crea un apunte de
  extracto). Con la caja YA CERRADA no se reabre ni se reescribe el cierre:
  el cierre es un hecho histórico. La reclasificación queda registrada y
  aparece aparte en los informes, para conciliarla a mano.

Un registro de corrección es inmutable: `write()` falla siempre. Si algo
estaba mal en la corrección, se registra otra. Mismo criterio que
`mgs.event.payment` (models/mgs_event.py).
"""
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .mgs_monthly_report import SOLD_STATES
from .mgs_permissions import require_manager

CORRECTION_TYPES = [
    ("sale", "Producto, cantidad o importe"),
    ("payment_method", "Método de pago"),
]


class MgsCorrection(models.Model):
    _name = "mgs.correction"
    _description = "Corrección trazable de una venta o un cobro"
    _order = "date desc, id desc"

    name = fields.Char("Referencia", readonly=True, copy=False)
    company_id = fields.Many2one("res.company", required=True, readonly=True,
                                 default=lambda s: s.env.company)
    date = fields.Datetime("Fecha", readonly=True, default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", "Confirmada por", readonly=True)
    correction_type = fields.Selection(CORRECTION_TYPES, string="Tipo", required=True, readonly=True)
    reason = fields.Text("Motivo", required=True, readonly=True)

    # --- Corrección de venta -----------------------------------------
    original_order_id = fields.Many2one("pos.order", "Venta original", readonly=True)
    return_order_id = fields.Many2one("pos.order", "Devolución rectificativa", readonly=True)
    new_sale_order_id = fields.Many2one("pos.order", "Venta correcta", readonly=True)

    # --- Reclasificación de cobro ------------------------------------
    original_payment_id = fields.Many2one("pos.payment", "Cobro original", readonly=True)
    original_method_id = fields.Many2one("pos.payment.method", "Método original", readonly=True)
    corrected_method_id = fields.Many2one("pos.payment.method", "Método correcto", readonly=True)
    amount = fields.Float("Importe reclasificado", readonly=True)
    session_id = fields.Many2one("pos.session", "Caja", readonly=True)
    session_was_open = fields.Boolean("La caja seguía abierta", readonly=True)
    statement_line_id = fields.Many2one("account.bank.statement.line", "Ajuste de efectivo",
                                        readonly=True)

    # --- Lo que se ve en el informe ----------------------------------
    original_value = fields.Float("Valor original", readonly=True)
    corrected_value = fields.Float("Corrección", readonly=True)
    resulting_value = fields.Float("Valor resultante", readonly=True)
    result_note = fields.Char("Resultado", readonly=True)

    # ------------------------------------------------------------------
    # Inmutabilidad
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Las correcciones se registran desde el asistente de corrección."))
        for vals in vals_list:
            vals.setdefault("name", self.env["ir.sequence"].next_by_code("mgs.correction") or "Nueva")
        return super().create(vals_list)

    def write(self, vals):
        raise AccessError(_(
            "Una corrección registrada no se modifica: si hay un error en ella, "
            "registra otra corrección."))

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("El historial de correcciones se conserva íntegro."))
        return super().unlink()

    # ------------------------------------------------------------------
    # Informes
    # ------------------------------------------------------------------
    @api.model
    def _mgs_report_rows(self, company, start, end):
        """Filas de la sección «Correcciones» (mgs_report_engine.correcciones).
        Muestra el valor original, la corrección y el resultado: la operación
        original nunca se oculta ni se sustituye."""
        types = dict(CORRECTION_TYPES)
        rows = []
        corrections = self.sudo().search([
            ("company_id", "=", company.id), ("date", ">=", start), ("date", "<", end),
        ])
        for correction in corrections:
            if correction.correction_type == "sale":
                original = correction.original_order_id.name or ""
            else:
                original = _("%(pedido)s · %(metodo)s") % {
                    "pedido": correction.original_payment_id.pos_order_id.name or "",
                    "metodo": correction.original_method_id.name or ""}
            rows.append({
                "date": fields.Datetime.context_timestamp(
                    self.env.user, correction.date).strftime("%d/%m/%Y %H:%M"),
                "name": correction.name or "",
                "type": types.get(correction.correction_type, ""),
                "original": original,
                "original_value": correction.original_value,
                "corrected_value": correction.corrected_value,
                "resulting_value": correction.resulting_value,
                "reason": correction.reason or "",
                "user": correction.user_id.name or "",
                "note": correction.result_note or "",
                # Para la vista previa, que usa `label`/`amount`.
                "label": "%s · %s" % (correction.name or "", types.get(correction.correction_type, "")),
                "amount": correction.corrected_value,
            })
        return rows


class MgsCorrectionWizard(models.TransientModel):
    """Asistente guiado: valida la corrección, ajusta el efectivo esperado si
    procede y deja el registro inmutable. Es el único camino para crear una
    `mgs.correction`."""
    _name = "mgs.correction.wizard"
    _description = "Registrar una corrección"

    correction_type = fields.Selection(CORRECTION_TYPES, string="Qué hay que corregir",
                                       required=True, default="sale")
    reason = fields.Text("Motivo", required=True,
                         help="Qué pasó y por qué se corrige. Queda en el historial y en los informes.")

    original_order_id = fields.Many2one("pos.order", "Venta original",
                                        domain="[('state', 'in', ('paid', 'done', 'invoiced'))]")
    return_order_id = fields.Many2one("pos.order", "Devolución rectificativa",
                                      domain="[('state', 'in', ('paid', 'done', 'invoiced'))]",
                                      help="La devolución ya registrada en el TPV que rectifica esa venta.")
    new_sale_order_id = fields.Many2one("pos.order", "Venta correcta (si se rehízo)",
                                        domain="[('state', 'in', ('paid', 'done', 'invoiced'))]")

    original_payment_id = fields.Many2one("pos.payment", "Cobro que se anotó mal")
    corrected_method_id = fields.Many2one("pos.payment.method", "Método correcto")
    amount = fields.Float("Importe a reclasificar")

    @api.onchange("original_payment_id")
    def _onchange_original_payment_id(self):
        if self.original_payment_id:
            self.amount = abs(self.original_payment_id.amount)

    def action_apply(self):
        self.ensure_one()
        require_manager(self.env)
        if not (self.reason or "").strip():
            raise UserError(_("Escribe el motivo de la corrección: queda en el historial."))
        values = {
            "correction_type": self.correction_type,
            "reason": self.reason.strip(),
            "user_id": self.env.uid,
            "company_id": self.env.company.id,
        }
        if self.correction_type == "sale":
            values.update(self._mgs_sale_values())
        else:
            values.update(self._mgs_payment_values())
        correction = self.env["mgs.correction"].sudo().create(values)
        return {
            "type": "ir.actions.act_window", "res_model": "mgs.correction",
            "res_id": correction.id, "view_mode": "form", "target": "current",
        }

    # ------------------------------------------------------------------
    def _mgs_sale_values(self):
        self.ensure_one()
        original = self.original_order_id
        devolucion = self.return_order_id
        if not original or not devolucion:
            raise UserError(_(
                "Indica la venta original y la devolución que la rectifica. La "
                "devolución se hace en el TPV («Ventas y devoluciones»); aquí solo "
                "se enlaza con su motivo."))
        if original.company_id != self.env.company or devolucion.company_id != self.env.company:
            raise UserError(_("Esas operaciones no son de esta tienda."))
        if original.state not in SOLD_STATES or devolucion.state not in SOLD_STATES:
            raise UserError(_("Solo se corrigen operaciones ya cobradas."))
        if devolucion == original:
            raise UserError(_("La devolución no puede ser la propia venta original."))
        # Esta es la comprobación que impide enlazar una devolución cualquiera:
        # alguna de sus líneas tiene que devolver una línea de ESA venta.
        if not any(line.refunded_orderline_id.order_id == original for line in devolucion.lines):
            raise UserError(_(
                "«%(devolucion)s» no devuelve ninguna línea de «%(original)s». Haz la "
                "devolución desde el ticket original para que quede vinculada.",
                devolucion=devolucion.name, original=original.name))
        if self.new_sale_order_id:
            if self.new_sale_order_id.company_id != self.env.company:
                raise UserError(_("Esa venta no es de esta tienda."))
            if self.new_sale_order_id.state not in SOLD_STATES:
                raise UserError(_("La venta correcta todavía no está cobrada."))
            if self.new_sale_order_id in (original, devolucion):
                raise UserError(_("La venta correcta tiene que ser una operación distinta."))
        resulting = original.amount_total + devolucion.amount_total + (
            self.new_sale_order_id.amount_total if self.new_sale_order_id else 0.0)
        note = _("Devolución %s") % devolucion.name
        if self.new_sale_order_id:
            note += _(" y venta nueva %s") % self.new_sale_order_id.name
        return {
            "original_order_id": original.id,
            "return_order_id": devolucion.id,
            "new_sale_order_id": self.new_sale_order_id.id or False,
            "original_value": original.amount_total,
            "corrected_value": devolucion.amount_total,
            "resulting_value": resulting,
            "result_note": note,
        }

    def _mgs_payment_values(self):
        self.ensure_one()
        payment = self.original_payment_id
        corrected = self.corrected_method_id
        if not payment or not corrected:
            raise UserError(_("Indica el cobro mal anotado y el método correcto."))
        if payment.pos_order_id.company_id != self.env.company:
            raise UserError(_("Ese cobro no es de esta tienda."))
        if corrected == payment.payment_method_id:
            raise UserError(_("El método correcto es el mismo que ya tiene el cobro."))
        if not math.isfinite(self.amount) or self.amount <= 0:
            raise UserError(_("El importe a reclasificar tiene que ser positivo."))
        if self.amount > abs(payment.amount) + 0.001:
            raise UserError(_(
                "No se puede reclasificar %(importe).2f: el cobro fue de %(cobro).2f.",
                importe=self.amount, cobro=abs(payment.amount)))
        session = payment.session_id
        # El cobro original se queda como está: lo que se registra es su
        # reclasificación. Ver la cabecera del módulo.
        statement_line = self.env["account.bank.statement.line"]
        session_open = bool(session) and session.state != "closed"
        moves_cash = payment.payment_method_id.is_cash_count != corrected.is_cash_count
        if session_open and moves_cash:
            statement_line = session._mgs_reclassify_cash(
                amount=self.amount,
                into_cash=corrected.is_cash_count,
                reason=_("Reclasificación de cobro: %(desde)s → %(hasta)s") % {
                    "desde": payment.payment_method_id.name, "hasta": corrected.name})
            note = _("Efectivo esperado ajustado en la caja %s") % session.name
        elif moves_cash:
            note = _(
                "Caja %s ya cerrada: el cierre no se reabre ni se reescribe. La "
                "reclasificación queda registrada para conciliarla aparte.") % (
                    session.name if session else "")
        else:
            note = _("Ni el método original ni el correcto son efectivo: el arqueo no cambia.")
        return {
            "original_payment_id": payment.id,
            "original_method_id": payment.payment_method_id.id,
            "corrected_method_id": corrected.id,
            "amount": self.amount,
            "session_id": session.id if session else False,
            "session_was_open": session_open,
            "statement_line_id": statement_line.id if statement_line else False,
            "original_value": payment.amount,
            "corrected_value": self.amount,
            # Una reclasificación no cambia lo cobrado, solo dónde se apunta.
            "resulting_value": payment.amount,
            "result_note": note,
        }


class PosSession(models.Model):
    _inherit = "pos.session"

    def _mgs_reclassify_cash(self, amount, into_cash, reason):
        """Ajusta el efectivo ESPERADO de una caja abierta por una
        reclasificación de cobro, con el mismo mecanismo que usa el TPV para
        entradas y salidas de efectivo (`try_cash_in_out`, que crea un apunte
        de extracto que `_compute_cash_balance` suma mientras la sesión no
        está cerrada). Devuelve el apunte creado.

        No se llama nunca con la caja cerrada: entonces
        `_compute_cash_balance` ya usa `cash_real_transaction` congelado y
        reescribir el cierre sería falsearlo."""
        self.ensure_one()
        if self.state == "closed":
            raise UserError(_("La caja ya está cerrada: su cierre no se reescribe."))
        if not self.cash_journal_id:
            raise UserError(_("Esta caja no tiene diario de efectivo."))
        before = self.statement_line_ids
        self.try_cash_in_out(
            "in" if into_cash else "out", amount, reason,
            {"translatedType": _("reclasificación")})
        self.invalidate_recordset(["statement_line_ids"])
        return (self.statement_line_ids - before)[:1]
