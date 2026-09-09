"""Deja el catálogo a cero antes de una entrega: borra los productos de la
tienda y su rastro (existencias, partidas, movimientos, ventas de TPV, avisos,
eventos y mermas), conservando TODA la configuración y las fichas técnicas
(DUA de l10n_es, Propinas del TPV, «Ramo a medida»).

Uso, con el servidor PARADO:

    python tools/reset_catalog.py -c "<ruta a odoo.local>" -d <base>

Pide confirmación escribiendo SI y hace una copia de seguridad antes de tocar
nada. No modifica usuarios, cajas, dispositivos, impuestos ni categorías.
"""
import argparse
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "odoo"))
import odoo

# Módulos cuyos productos son técnicos y se conservan (los instala el propio
# stack: localización fiscal, TPV, contabilidad, y la composición del módulo).
KEEP_MODULES = ("l10n_es", "point_of_sale", "account", "product", "mi_gestor_stock")


def _shop_products(env):
    """product.template que NO son fichas técnicas de ningún módulo."""
    templates = env["product.template"].with_context(active_test=False).search([])
    protected = set(env["ir.model.data"].search([
        ("model", "=", "product.template"),
        ("res_id", "in", templates.ids),
        ("module", "in", list(KEEP_MODULES)),
    ]).mapped("res_id"))
    return templates.filtered(lambda t: t.id not in protected)


def reset_catalog(database, assume_yes=False):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database):
        raise ValueError("Nombre de base no válido")
    registry = odoo.modules.registry.Registry(database)
    with registry.cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        templates = _shop_products(env)
        if not templates:
            print("El catálogo ya está vacío: no hay productos de tienda que borrar.")
            return
        variants = templates.with_context(active_test=False).mapped("product_variant_ids")
        print("Se van a borrar %s productos (%s variantes) y todo su historial:"
              % (len(templates), len(variants)))
        for tmpl in templates[:40]:
            print("  -", tmpl.display_name)
        if len(templates) > 40:
            print("  ... y %s más" % (len(templates) - 40))

        if not assume_yes:
            if input('\nEscribe SI para continuar: ').strip() != "SI":
                print("Cancelado. No se ha borrado nada.")
                return

        print("Haciendo copia de seguridad...")
        backup = env["mgs.backup"].sudo()._mgs_run_backup(kind="manual")
        if not backup or backup.state != "done":
            raise RuntimeError("La copia de seguridad no se completó; no se continúa. "
                               "Revisa Configuración → Copias de seguridad.")
        print("Copia hecha en", backup.path)

        product_ids = tuple(variants.ids)

        # 1. Ventas de TPV de esos productos -> sus pedidos -> sesiones vacías.
        lines = env["pos.order.line"].search([("product_id", "in", product_ids)])
        orders = lines.mapped("order_id")
        sessions = orders.mapped("session_id")
        env["mgs.bouquet.component"].sudo().search(
            [("line_id", "in", lines.ids)]).unlink()
        lines.unlink()
        empty_orders = orders.filtered(lambda o: not o.lines)
        empty_orders.write({"state": "cancel"})
        empty_orders.unlink()
        for session in sessions.filtered(lambda s: not s.order_ids):
            session.write({"state": "closed"})
        sessions.filtered(lambda s: not s.order_ids).unlink()

        # 2. Eventos que solo tocan productos de tienda (líneas y componentes).
        event_lines = env["mgs.event.line"].search([("product_id", "in", product_ids)])
        events = event_lines.mapped("event_id")
        env["mgs.event.line.component"].sudo().search(
            [("line_id", "in", event_lines.ids)]).unlink()
        event_lines.unlink()
        events.filtered(lambda e: not e.line_ids).unlink()

        # 3. Mermas, avisos y bajas de esos productos.
        env["stock.scrap"].search([("product_id", "in", product_ids)]).unlink()
        tmpl_ids = tuple(templates.ids)
        env["mgs.stock.alert"].with_context(active_test=False).search(
            [("product_id", "in", tmpl_ids)]).unlink()
        env["mgs.stock.alert.notice"].search([("product_id", "in", tmpl_ids)]).unlink()

        # 4. Movimientos, líneas, reservas, existencias y partidas.
        env["stock.move.line"].search([("product_id", "in", product_ids)]).unlink()
        env["stock.move"].search([("product_id", "in", product_ids)]).unlink()
        env["stock.quant"].with_context(inventory_mode=False).search(
            [("product_id", "in", product_ids)]).sudo().unlink()
        env["stock.lot"].search([("product_id", "in", product_ids)]).unlink()

        # 5. Los productos.
        variants.with_context(active_test=False).unlink()
        templates.with_context(active_test=False).unlink()

        cr.commit()
        print("\nCatálogo vacío. Se conservan configuración, usuarios, caja, "
              "dispositivos, impuestos y categorías.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", default=str(PROJECT / "odoo.conf"))
    parser.add_argument("-d", "--database", required=True)
    parser.add_argument("--yes", action="store_true", help="No preguntar (para scripts)")
    args = parser.parse_args()
    odoo.tools.config.parse_config(["-c", args.config, "-d", args.database, "--no-http"])
    reset_catalog(args.database, assume_yes=args.yes)


if __name__ == "__main__":
    main()
