# -*- coding: utf-8 -*-
"""Acceso solo con contraseña — normalización de la cuenta en bases existentes.

Hasta ahora el instalador renombraba la cuenta administradora a `propietaria`,
así que el uso diario iba con permisos de administración técnica de Odoo. Esta
migración, sobre una base que venga de esa situación:

  * devuelve a la cuenta administradora su login (`admin`) y la deja como
    cuenta técnica de rotura de cristal — se conserva activa y con su
    contraseña hasta que se compruebe el nuevo acceso (el plan pide no
    deshabilitarla antes de verificar);
  * crea una cuenta `propietaria` nueva con permisos de **gestión de tienda**
    y sin administración técnica, marcada como la cuenta del formulario de
    acceso;
  * deja el primer acceso **pendiente**: genera un código de activación y lo
    escribe una sola vez en `<data_dir>/<base>-activacion.txt`. La dueña fija
    su contraseña y obtiene su clave de recuperación en `/mgs/primer-acceso`.

No toca ventas, autorías ni historial: la cuenta antigua (ahora `admin`)
conserva todo lo que creó. Si la base no viene de esa situación (no hay login
`propietaria`, o ya hay una cuenta de propietaria marcada) no hace nada.
"""
import logging
import secrets

from odoo import SUPERUSER_ID, api
from odoo.tools import config

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Users = env["res.users"].sudo()

    if Users.search_count([("mgs_is_owner", "=", True)]):
        return

    admin = env.ref("base.user_admin", raise_if_not_found=False)
    if not admin or admin.login != "propietaria":
        _logger.info(
            "mi_gestor_stock: la cuenta administradora no está renombrada a "
            "«propietaria»; no se provisiona ninguna cuenta de propietaria en "
            "la migración.")
        return

    manager_group = env.ref("mi_gestor_stock.group_mgs_manager")

    # 1) La cuenta administradora recupera su login y se queda de reserva.
    admin.write({"login": "admin"})
    _logger.warning(
        "mi_gestor_stock: la cuenta administradora vuelve a llamarse «admin» y "
        "queda solo como cuenta técnica. Deshabilita su acceso diario cuando "
        "hayas comprobado el nuevo acceso de la propietaria.")

    # 2) Cuenta de propietaria: gestión de tienda, sin administración técnica.
    owner = Users.create({
        "name": "Propietaria",
        "login": "propietaria",
        "password": secrets.token_urlsafe(48),  # inutilizable hasta el primer acceso
        "groups_id": [(6, 0, [manager_group.id])],
        "lang": "es_ES",
        "tz": "Europe/Madrid",
        "mgs_is_owner": True,
    })
    home = env.ref("mi_gestor_stock.action_mgs_home", raise_if_not_found=False)
    if home:
        owner.action_id = home.id

    # 3) Primer acceso pendiente + código de activación en un archivo local.
    code = env["mgs.access"].sudo()._begin_activation(owner)
    env["mgs.access"].sudo()._log_event(
        "primer-acceso",
        "Cuenta de propietaria creada en la migración; primer acceso pendiente.")

    written = _write_activation_file(cr.dbname, code, config.get("data_dir") or "")
    banner = (
        "\n" + "=" * 72 +
        "\n  PRIMER ACCESO DE LA PROPIETARIA — código de activación"
        "\n  " + ("archivo: " + written if written else "código: " + code) +
        "\n  Entra en /mgs/primer-acceso, escribe el código y elige la contraseña."
        "\n" + "=" * 72 + "\n")
    _logger.warning("mi_gestor_stock:%s", banner)


def _write_activation_file(dbname, code, data_dir):
    try:
        import os
        from datetime import datetime

        target_dir = data_dir or os.getcwd()
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, f"{dbname}-activacion.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "Código de activación para el primer acceso de la propietaria\n"
                f"Base de datos: {dbname}\n"
                f"Generado: {datetime.now().isoformat(timespec='seconds')}\n\n"
                f"    {code}\n\n"
                "Abre el programa, ve a «He olvidado mi contraseña» -> no; entra en\n"
                "/mgs/primer-acceso, escribe este código y elige tu contraseña (12+\n"
                "caracteres). Después guarda la clave de recuperación que te dé.\n"
                "Borra este archivo cuando termines.\n")
        return path
    except OSError:
        _logger.exception("mi_gestor_stock: no se pudo escribir el archivo de activación")
        return None
