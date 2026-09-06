from odoo import _
from odoo.exceptions import AccessError


MANAGER_GROUPS = (
    "mi_gestor_stock.group_mgs_manager", "stock.group_stock_manager",
    "point_of_sale.group_pos_manager", "base.group_system",
)
COST_GROUPS = ",".join(MANAGER_GROUPS)


def is_manager(env):
    return env.su or any(env.user.has_group(group) for group in MANAGER_GROUPS)


def require_manager(env):
    if not is_manager(env):
        raise AccessError(env._("Esta operación está reservada a la responsable de la tienda."))


def require_operator(env):
    if not (is_manager(env) or env.user.has_group("mi_gestor_stock.group_mgs_user")):
        raise AccessError(env._("No tienes permiso para utilizar los dispositivos de la tienda."))


def checked_session(env, session_id):
    require_operator(env)
    session = env["pos.session"].browse(session_id).exists()
    session.check_access("read")
    if not session or session.company_id != env.company:
        raise AccessError(env._("La caja no pertenece a esta tienda."))
    if not is_manager(env) and session.user_id != env.user:
        raise AccessError(env._("Solo puedes operar en tu sesión de caja."))
    return session
