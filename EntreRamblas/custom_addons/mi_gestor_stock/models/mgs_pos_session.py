import logging

from odoo import api, fields, models, SUPERUSER_ID
from odoo.modules.registry import Registry

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

    def _validate_session(self, *args, **kwargs):
        result = super()._validate_session(*args, **kwargs)
        closed = self.filtered(lambda session: session.state == "closed")
        if closed and self.env["mgs.config"]._mgs_get().backup_enabled:
            closed.sudo().write({"mgs_backup_pending": True})
            dbname = self.env.cr.dbname
            self.env.cr.postcommit.add(lambda: backup_after_close(dbname))
        return result
