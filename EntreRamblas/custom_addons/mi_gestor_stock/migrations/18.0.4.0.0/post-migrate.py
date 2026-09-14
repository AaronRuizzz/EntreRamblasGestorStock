# -*- coding: utf-8 -*-
"""18.0.4.0.0 — provisión uniforme de la propietaria y limpieza de secretos.

Sobre cualquier base ya instalada (venga de `admin`, de `propietaria` o de una
propietaria a medias):

  * provisiona/normaliza la cuenta de la propietaria con la MISMA rutina que el
    instalador (`mgs.access._mgs_provision_owner`): un solo camino, dos
    llamadores. Idempotente; no toca ventas ni autorías. La cuenta `admin` se
    conserva utilizable como reserva hasta comprobar el nuevo acceso.
  * si el primer acceso queda pendiente, escribe el código de activación en
    `<data_dir>/<base>-activacion.txt`. Si NO se puede escribir el archivo, el
    código NO se imprime en el log: el estado queda `pending` y se recupera con
    `recuperar-acceso.ps1`.
  * borra los secretos que versiones anteriores del asistente
    `mgs.access.regenerate` dejaban en claro en la tabla (contraseña actual y
    clave nueva). El modelo es transitorio pero sus filas podían entrar en una
    copia antes del vacío.
"""
import logging
import os
from datetime import datetime

from odoo import SUPERUSER_ID, api
from odoo.tools import config

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    # 1) Secretos en claro del asistente de regeneración: fuera. Los campos
    # pasan a store=False (no vuelven a escribirse), pero un -u normal NO
    # elimina columnas ya existentes por su cuenta: sin este DROP explícito,
    # la contraseña y la clave que hubiera quedaban en la tabla igualmente.
    cr.execute("""
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'mgs_access_regenerate'
    """)
    if cr.fetchone():
        cr.execute("DELETE FROM mgs_access_regenerate")
        _logger.info("mi_gestor_stock: filas del asistente de regeneración purgadas (%s)",
                     cr.rowcount)
        for column in ("current_password", "new_key"):
            cr.execute("""
                SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'mgs_access_regenerate' AND column_name = %s
            """, [column])
            if cr.fetchone():
                cr.execute('ALTER TABLE mgs_access_regenerate DROP COLUMN "%s"' % column)
        _logger.info("mi_gestor_stock: columnas de secretos del asistente eliminadas")

    # 2) Provisión uniforme de la propietaria.
    code = env["mgs.access"].sudo()._mgs_provision_owner(neutralize_admin=False)
    if not code:
        _logger.info("mi_gestor_stock: la cuenta de propietaria ya estaba provisionada.")
        return

    written = _write_activation_file(cr.dbname, code, config.get("data_dir") or "")
    if written:
        _logger.warning(
            "mi_gestor_stock: PRIMER ACCESO PENDIENTE — código de activación en %s. "
            "Entra en /mgs/primer-acceso.", written)
    else:
        _logger.error(
            "mi_gestor_stock: PRIMER ACCESO PENDIENTE pero no se pudo escribir el "
            "archivo de activación. NO se registra el código en el log: ejecuta "
            "recuperar-acceso.ps1 para emitir uno nuevo.")


def _write_activation_file(dbname, code, data_dir):
    if not data_dir:
        return None
    try:
        os.makedirs(data_dir, exist_ok=True)
        path = os.path.join(data_dir, f"{dbname}-activacion.txt")
        with open(path, "w", encoding="utf-8") as fh:  # la migración rota el código; el archivo se reescribe
            fh.write(
                "Codigo de activacion para el primer acceso de la propietaria\n"
                f"Base de datos: {dbname}\n"
                f"Generado: {datetime.now().isoformat(timespec='seconds')}\n\n"
                f"    {code}\n\n"
                "Entra en /mgs/primer-acceso, escribe este codigo y elige tu\n"
                "contrasena (12+ caracteres). Guarda despues la clave de\n"
                "recuperacion. Borra este archivo cuando termines.\n")
        return path
    except OSError:
        return None
