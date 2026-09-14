# -*- coding: utf-8 -*-
"""18.0.4.0.0 — cambios de modelo de xmlid que un -u no puede aplicar solo.

`action_mgs_security` pasa de `ir.actions.server` (tipo code) a
`ir.actions.act_window` (hallazgo 14: un server action de tipo code sin
`groups_id` exige permiso de ESCRITURA sobre el modelo antes de ejecutarse, y la
propietaria solo tiene lectura sobre `mgs.access`). Odoo no deja que un external
id cambie de modelo, así que se borra el registro antiguo para que el -u lo
recree como ventana.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        SELECT d.res_id FROM ir_model_data d
         WHERE d.module = 'mi_gestor_stock'
           AND d.name = 'action_mgs_security'
           AND d.model = 'ir.actions.server'
    """)
    row = cr.fetchone()
    if not row:
        return
    action_id = row[0]
    cr.execute("UPDATE ir_ui_menu SET action = NULL WHERE action = %s",
               ["ir.actions.server,%d" % action_id])
    cr.execute("DELETE FROM ir_act_server WHERE id = %s", [action_id])
    cr.execute("DELETE FROM ir_actions WHERE id = %s", [action_id])
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'mi_gestor_stock' AND name = 'action_mgs_security'
    """)
    _logger.info("mi_gestor_stock: action_mgs_security antiguo (server #%s) retirado; "
                 "el -u lo recrea como ventana.", action_id)
