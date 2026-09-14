import logging

from odoo import api, fields, models, SUPERUSER_ID
from odoo.modules.registry import Registry

from .mgs_permissions import assert_not_maintenance

_logger = logging.getLogger(__name__)


def backup_after_close(dbname):
    try:
        with Registry(dbname).cursor() as cr:
            api.Environment(cr, SUPERUSER_ID, {})["mgs.backup"]._mgs_backup_closed_sessions()
            cr.commit()
    except Exception:
        _logger.exception("Copia de cierre pendiente; el cron volverá a intentarla")


class PosSession(models.Model):
    _inherit = "pos.session"

    mgs_backup_pending = fields.Boolean("Copia de cierre pendiente", readonly=True, copy=False)

    def message_post(self, **kwargs):
        """Abrir/cerrar caja publica un mensaje con el usuario actual como autor.
        Si la propietaria no tiene correo (y no queremos exigirlo en el
        registro), Odoo abortaba la operacion. Se suministra un remitente local
        NO enrutable derivado del dominio de alias de la empresa."""
        if not self.env.su and not kwargs.get("author_id") and not kwargs.get("email_from"):
            if not self.env.user.partner_id.email:
                company = self.env.company
                kwargs["email_from"] = (
                    company.email
                    or getattr(company, "default_from_email", False)
                    or "tienda@entreramblas.invalid")
        return super().message_post(**kwargs)

    def _validate_session(self, *args, **kwargs):
        result = super()._validate_session(*args, **kwargs)
        closed = self.filtered(lambda session: session.state == "closed")
        if closed and self.env["mgs.config"]._mgs_get().backup_enabled:
            closed.sudo().write({"mgs_backup_pending": True})
            dbname = self.env.cr.dbname
            self.env.cr.postcommit.add(lambda: backup_after_close(dbname))
        return result

    def set_opening_control(self, cashbox_value, notes):
        # Abrir caja es el punto de entrada real de "operación nueva" para el
        # TPV (hallazgo 11): con mgs.maintenance puesto, no se abre.
        assert_not_maintenance(self.env)
        return super().set_opening_control(cashbox_value, notes)


class PosConfig(models.Model):
    _inherit = "pos.config"

    def open_ui(self):
        assert_not_maintenance(self.env)
        return super().open_ui()
