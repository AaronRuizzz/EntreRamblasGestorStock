"""Outbox de hardware: confirmar intención antes de enviar bytes, sin reenvío incierto."""
import base64
import logging
from uuid import UUID, uuid4

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.modules.registry import Registry
from odoo.exceptions import UserError
from .mgs_permissions import require_operator, require_manager, checked_session, COST_GROUPS
from .mgs_escpos import EscposDocument

_logger = logging.getLogger(__name__)


def dispatch_job(dbname, job_id):
    # Esta transacción es independiente de la venta y de la petición HTTP.
    # Un reinicio tras confirmar 'sending' nunca provoca un segundo envío.
    try:
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            cr.execute("SELECT id FROM mgs_hardware_job WHERE id = %s FOR UPDATE", [job_id])
            job = env["mgs.hardware.job"].browse(job_id).exists()
            if not job or job.state != "pending":
                return
            job.state = "sending"
            cr.commit()
            try:
                config = env["mgs.config"].with_company(job.company_id)._mgs_get()
                config._mgs_send(base64.b64decode(job.payload), job.reason)
            except Exception as error:
                job.write({"state": "uncertain", "message": str(error)})
            else:
                job.write({"state": "sent", "message": "Enviado al dispositivo; comprueba el resultado físico."})
                if job.kind == "receipt":
                    cr.execute("UPDATE pos_order SET nb_print = COALESCE(nb_print, 0) + 1 WHERE id = %s", [job.order_id.id])
            cr.commit()
    except Exception:
        # La intención permanece pendiente o en sending. Solo pending se recupera.
        _logger.exception("No se pudo procesar la solicitud de hardware %s", job_id)


class HardwareJob(models.Model):
    _name = "mgs.hardware.job"
    _description = "Registro de impresiones y aperturas de cajón"
    _order = "id desc"

    request_key = fields.Char(required=True, readonly=True, index=True)
    kind = fields.Selection([("receipt", "Ticket"), ("drawer", "Apertura de cajón")], required=True, readonly=True)
    state = fields.Selection([
        ("pending", "Pendiente"), ("sending", "Envío iniciado, resultado sin confirmar"),
        ("sent", "Enviado"), ("uncertain", "Resultado incierto"),
    ], default="pending", required=True, readonly=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True)
    user_id = fields.Many2one("res.users", required=True, readonly=True)
    session_id = fields.Many2one("pos.session", readonly=True)
    order_id = fields.Many2one("pos.order", readonly=True)
    reason = fields.Char(required=True, readonly=True)
    message = fields.Char(readonly=True)
    payload = fields.Binary(required=True, attachment=False, readonly=True, groups=COST_GROUPS)

    _sql_constraints = [("request_key_unique", "unique(request_key)", "Esta solicitud ya está registrada.")]

    @api.model
    def _enqueue(self, key, kind, payload, reason, session=None, order=None):
        # El candado transaccional serializa peticiones con la misma clave.
        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])
        job = self.sudo().search([("request_key", "=", key)], limit=1)
        existing = bool(job)
        if not job:
            job = self.sudo().create({
                "request_key": key, "kind": kind, "payload": base64.b64encode(payload),
                "reason": reason, "user_id": self.env.uid, "company_id": self.env.company.id,
                "session_id": session.id if session else False, "order_id": order.id if order else False,
            })
        if job.state == "pending":
            dbname, job_id = self.env.cr.dbname, job.id
            self.env.cr.postcommit.add(lambda: dispatch_job(dbname, job_id))
        return {"id": job.id, "state": job.state, "existing": existing}

    @api.model
    def _cron_dispatch(self):
        for job in self.sudo().search([("state", "=", "pending")], limit=50):
            dispatch_job(self.env.cr.dbname, job.id)


class Config(models.Model):
    _inherit = "mgs.config"

    def _mgs_checked_order(self, order_id):
        require_operator(self.env)
        order = self.env["pos.order"].browse(order_id).exists()
        order.check_access("read")
        if not order or order.company_id != self.env.company:
            raise UserError(_("La venta no pertenece a esta tienda."))
        checked_session(self.env, order.session_id.id)
        if order.state not in ("paid", "done", "invoiced"):
            raise UserError(_("La venta debe estar confirmada antes de usar el hardware."))
        return order

    @api.model
    def mgs_pos_print_order(self, order_id, reprint_key=None):
        order = self._mgs_checked_order(order_id)
        config = self._mgs_get()
        if config.printer_mode == "disabled":
            return {"state": "disabled"}
        key = "receipt:%s:auto" % order.id
        if reprint_key:
            try:
                key = "receipt:%s:%s" % (order.id, UUID(reprint_key))
            except (ValueError, TypeError, AttributeError):
                raise UserError(_("Identificador de reimpresión no válido."))
        return self.env["mgs.hardware.job"]._enqueue(
            key, "receipt", config._mgs_pos_ticket(order.sudo()).to_bytes(),
            _("Reimpresión solicitada") if reprint_key else _("Ticket de venta"), order.session_id, order)

    @api.model
    def mgs_pos_open_drawer(self, order_id=None):
        require_operator(self.env)
        if not order_id:
            raise UserError(_("Indica la venta o utiliza la apertura manual con motivo."))
        order = self._mgs_checked_order(order_id)
        if not order.payment_ids.filtered(lambda p: p.payment_method_id.is_cash_count and p.amount):
            raise UserError(_("La venta no contiene un movimiento de efectivo."))
        return self._mgs_queue_drawer("drawer:%s:sale" % order.id, _("Cobro en efectivo"), order.session_id, order)

    @api.model
    def mgs_pos_manual_drawer(self, session_id, reason, request_key):
        session = checked_session(self.env, session_id)
        if session.state not in ("opening_control", "opened", "closing_control"):
            raise UserError(_("La sesión de caja está cerrada."))
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 200:
            raise UserError(_("Escribe un motivo de apertura de hasta 200 caracteres."))
        try:
            key = "drawer:%s:%s" % (session.id, UUID(request_key))
        except (ValueError, TypeError, AttributeError):
            raise UserError(_("Identificador de apertura no válido."))
        return self._mgs_queue_drawer(key, reason.strip(), session)

    def _mgs_queue_drawer(self, key, reason, session=None, order=None):
        config = self._mgs_get()
        if not config.drawer_enabled or config.printer_mode == "disabled" or (order and not config.drawer_on_sale):
            return {"state": "disabled"}
        doc = EscposDocument()
        doc.open_drawer(pin=int(config.drawer_pin or "0"), on_ms=config.drawer_pulse_ms or 100,
                        off_ms=(config.drawer_pulse_ms or 100) * 2)
        return self.env["mgs.hardware.job"]._enqueue(key, "drawer", doc.to_bytes(), reason, session, order)

    def action_mgs_open_drawer(self):
        require_manager(self.env)
        result = self._mgs_queue_drawer("drawer:test:%s" % uuid4(), _("Prueba de instalación por la responsable"))
        return self._mgs_notify(_("Solicitud de apertura registrada.") if result["state"] != "disabled" else _("Cajón desactivado."))

    def mgs_open_drawer(self):
        return self.action_mgs_open_drawer()

    @api.model
    def mgs_pos_job_status(self, job_id):
        require_operator(self.env)
        job = self.env["mgs.hardware.job"].browse(job_id).exists()
        job.check_access("read")
        if not job:
            raise UserError(_("No se encuentra la solicitud."))
        return {"id": job.id, "state": job.state, "message": job.message,
                "nb_print": job.order_id.nb_print if job.order_id else 0}
