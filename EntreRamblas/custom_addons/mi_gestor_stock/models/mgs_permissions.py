from datetime import datetime, time, timedelta

import pytz

from odoo import _
from odoo.exceptions import AccessError, UserError


MANAGER_GROUPS = (
    "mi_gestor_stock.group_mgs_manager", "stock.group_stock_manager",
    "point_of_sale.group_pos_manager", "base.group_system",
)
COST_GROUPS = ",".join(MANAGER_GROUPS)

MAINTENANCE_PARAM = "mgs.maintenance"


def is_manager(env):
    return env.su or any(env.user.has_group(group) for group in MANAGER_GROUPS)


def in_maintenance(env):
    """El actualizador escribe `mgs.maintenance` (con la marca de tiempo en
    que empezó) justo antes de copiar y aplicar una actualización, y lo borra
    al terminar o al revertir. Antes se escribía y se borraba pero ningún
    código de la aplicación lo consultaba (hallazgo 11): no bloqueaba nada."""
    return bool(env["ir.config_parameter"].sudo().get_param(MAINTENANCE_PARAM))


def assert_not_maintenance(env):
    if in_maintenance(env):
        raise UserError(_(
            "La aplicación se está actualizando. Esto dura solo un momento: "
            "espera y vuelve a intentarlo."))


def require_manager(env):
    assert_not_maintenance(env)
    if not is_manager(env):
        raise AccessError(env._("Esta operación está reservada a la responsable de la tienda."))


def require_operator(env):
    assert_not_maintenance(env)
    if not (is_manager(env) or env.user.has_group("mi_gestor_stock.group_mgs_user")):
        raise AccessError(env._("No tienes permiso para utilizar los dispositivos de la tienda."))


def madrid_day_range(env, date_from, date_to):
    """Convierte un rango de días de Madrid (ambos inclusive) en el rango
    [start, end) de datetimes UTC sin zona horaria que usan las consultas de
    informes: `start` es la medianoche de Madrid de `date_from`, `end` la
    medianoche de Madrid del día SIGUIENTE a `date_to` (exclusivo).

    Extraído de mgs.monthly.report._mgs_period sin cambiar el cálculo: los
    informes personalizados (mgs_report_engine.py) lo reutilizan tal cual
    para no arriesgarse a que los dos calculen "hoy en Madrid" de forma
    distinta cerca de la medianoche."""
    if not date_from or not date_to or date_from > date_to:
        raise UserError(env._("Selecciona un periodo válido: la fecha inicial no puede superar la final."))
    zone = pytz.timezone("Europe/Madrid")
    return tuple(
        zone.localize(datetime.combine(day, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        for day in (date_from, date_to + timedelta(days=1)))


def checked_session(env, session_id):
    require_operator(env)
    session = env["pos.session"].browse(session_id).exists()
    session.check_access("read")
    if not session or session.company_id != env.company:
        raise AccessError(env._("La caja no pertenece a esta tienda."))
    if not is_manager(env) and session.user_id != env.user:
        raise AccessError(env._("Solo puedes operar en tu sesión de caja."))
    return session
