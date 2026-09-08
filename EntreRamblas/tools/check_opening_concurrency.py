"""Carrera real entre apertura de existencias y recepción, con dos conexiones.

La apertura solo admite productos sin movimientos ni existencias. Esa condición
se comprueba dentro de una transacción, así que solo se sostiene si la recepción
—el único flujo que puede crear las primeras existencias de un producto— toma el
mismo candado sobre `product_product`. Aquí se demuestra con dos transacciones
abiertas a la vez: la segunda tiene que quedarse esperando (un `lock_timeout`
corto la corta) en vez de colarse entre la comprobación y el ajuste.

La apertura se deja preparada y confirmada ANTES de la carrera: así lo que espera
es `action_apply`, no el alta de las líneas. Ninguna de las dos transacciones de
la carrera llega a confirmarse y el material de apoyo se borra al terminar. Que
una recepción ya confirmada cierra la puerta a la apertura lo comprueba
`tests/test_opening_stock.py`. Usa la base aislada de validación.
"""
import sys
from pathlib import Path
from uuid import uuid4

import psycopg2

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "odoo"))
import odoo
from odoo import api, Command, SUPERUSER_ID
from odoo.modules.registry import Registry

odoo.tools.config.parse_config([
    "-c", str(root / "odoo.conf"), "--db_host=127.0.0.1", "--db_port=55432",
    "--db_user=mgs_test", "-d", "mgs_validation", "--http-interface=127.0.0.1",
])
DB = "mgs_validation"
reg = Registry(DB)
TAG = uuid4().hex[:8]


def env_of(cr):
    return api.Environment(cr, SUPERUSER_ID, {})


def fixture():
    """Producto, ubicación y apertura en borrador, visibles desde las dos conexiones."""
    with reg.cursor() as cr:
        env = env_of(cr)
        warehouse = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        product = env["product.product"].create({
            "name": "Concurrencia %s" % TAG, "is_storable": True,
            "tracking": "lot", "mgs_auto_lots": True, "use_expiration_date": True,
        })
        location = env["stock.location"].create({
            "name": "Concurrencia %s" % TAG, "usage": "internal",
            "location_id": warehouse.lot_stock_id.id, "company_id": env.company.id,
        })
        openings = env["mgs.opening.stock"].create([{
            "name": "Apertura %s %s" % (TAG, index), "location_id": location.id,
            "line_ids": [Command.create({"product_id": product.id, "quantity": 5,
                                         "unit_cost": 2, "checked": True})],
        } for index in (1, 2)])
        cr.commit()
        return product.id, location.id, openings.ids


def hold_reception(cr, product_id):
    """Recepción confirmada y SIN confirmar la transacción: se queda con el candado."""
    env_of(cr)["mgs.reception"].create({
        "line_ids": [Command.create({"product_id": product_id, "quantity": 4, "unit_cost": 3})],
    }).action_confirm()


def hold_opening(cr, opening_id):
    env_of(cr)["mgs.opening.stock"].browse(opening_id).action_apply()


def blocked(cr, action):
    """Ejecuta `action` con un tiempo de espera corto: True si el candado la detiene."""
    cr.execute("SET LOCAL lock_timeout = '2s'")
    try:
        action(cr)
    except psycopg2.errors.LockNotAvailable:
        return True
    return False


def race(first, second, label):
    holder, waiter = reg.cursor(), reg.cursor()
    try:
        first(holder)                      # Transacción A: toma el candado, no confirma.
        waited = blocked(waiter, second)   # Transacción B: tiene que quedarse esperando.
        assert waited, "%s: la segunda transacción no esperó al candado" % label
        print("OK %s: la segunda operación espera al candado del producto" % label)
    finally:
        # Ninguna de las dos se confirma: la base queda como estaba.
        for cursor in (waiter, holder):
            cursor.rollback()
            cursor.close()


def cleanup(product_id, location_id, opening_ids):
    with reg.cursor() as cr:
        env = env_of(cr)
        assert not env["stock.move"].search_count([("product_id", "=", product_id)]), \
            "La prueba ha dejado movimientos confirmados: revisa el rollback"
        assert not env["stock.quant"].search_count([("product_id", "=", product_id)]), \
            "La prueba ha dejado existencias: revisa el rollback"
        env["mgs.opening.stock"].browse(opening_ids).exists().unlink()
        product = env["product.product"].browse(product_id)
        product.write({"available_in_pos": False})  # El TPV protege sus productos.
        product.unlink()
        env["stock.location"].browse(location_id).unlink()
        cr.commit()
    print("OK: la base de validación queda sin rastro de la prueba")


product_id, location_id, opening_ids = fixture()
try:
    race(lambda cr: hold_reception(cr, product_id),
         lambda cr: hold_opening(cr, opening_ids[0]),
         "recepción abierta / apertura después")
    race(lambda cr: hold_opening(cr, opening_ids[0]),
         lambda cr: hold_reception(cr, product_id),
         "apertura abierta / recepción después")
    race(lambda cr: hold_opening(cr, opening_ids[0]),
         lambda cr: hold_opening(cr, opening_ids[1]),
         "dos aperturas del mismo producto")
finally:
    cleanup(product_id, location_id, opening_ids)
print("OK: apertura y recepción se serializan sobre el mismo candado de producto")
