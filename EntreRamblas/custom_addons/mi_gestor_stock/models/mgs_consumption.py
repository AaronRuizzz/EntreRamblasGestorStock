# -*- coding: utf-8 -*-
"""Consumo real de flor: cuántas rosas se gastan de verdad, no cuántos
«Ramo a medida» se han vendido.

Un ramo de 12 rosas sale en «Productos más vendidos» como 1 unidad de «Ramo a
medida» (mgs_monthly_report.py agrega por línea de venta) — el dato que hace
falta para comprar, cuántas rosas se consumen, se pierde. Ese detalle SÍ está
guardado, en `mgs.bouquet.component`, pero explotarlo solo ahí dejaría fuera
lo vendido suelto y lo entregado en eventos, y no llevaría coste.

Por eso esta vista lee `stock.move.line`, que es donde YA está todo unificado
con su coste histórico congelado: una rosa suelta, una rosa dentro de un ramo
y una rosa de un centro de un evento son, todas, líneas de movimiento con
`mgs_unit_cost`. Filtrar por `location_dest_id.usage = 'customer'` basta para
quedarse solo con lo que de verdad ha salido de la tienda: excluye mermas,
devoluciones (van en dirección contraria) y el material de alquiler que
vuelve (va a la ubicación de tránsito, no a «cliente»).

Las mermas NO se incluyen a propósito: ya tienen su propio apartado en el
informe mensual, con sus motivos (deterioro/caducidad/rotura/devolución).
Mezclarlas aquí confundiría «lo que se ha vendido» con «lo que se ha tirado».

OJO con esto al tocar el modelo: al ser una vista SQL sobre OTRAS tablas
(stock_move_line, stock_move...), buscar aquí NO vuelca solo las escrituras
pendientes de mgs.flower.consumption (no tiene ninguna: no se escribe nunca),
así que un cambio reciente en esas otras tablas, dentro de la MISMA
transacción, puede no verse todavía si nadie las ha volcado antes. Por eso
`search()` fuerza `flush_all()` explícitamente antes de preguntar."""
from odoo import fields, models, tools


class MgsFlowerConsumption(models.Model):
    _name = "mgs.flower.consumption"
    _description = "Consumo real de flor y material (solo lectura)"
    _auto = False
    _order = "date desc"

    date = fields.Datetime(readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Categoría", readonly=True)
    uom_id = fields.Many2one("uom.uom", string="Unidad", readonly=True)
    quantity = fields.Float(readonly=True)
    cost = fields.Float(readonly=True, groups="mi_gestor_stock.group_mgs_manager")
    origin = fields.Selection([
        ("pos", "Venta suelta"),
        ("bouquet", "Componente de ramo"),
        ("event", "Evento o encargo"),
    ], readonly=True)
    partner_id = fields.Many2one("res.partner", string="Cliente", readonly=True)
    pos_order_id = fields.Many2one("pos.order", string="Venta", readonly=True)
    event_id = fields.Many2one("mgs.event", string="Evento", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    def _search(self, domain, offset=0, limit=None, order=None):
        # El punto bajo de verdad: search(), search_count(), search_read()
        # y read_group() (las vistas pivot/graph pasan por aqui) acaban
        # todos en _search(), no todos pasan por search(). Volcarlo aqui,
        # no arriba, es lo unico que cubre los cuatro caminos.
        self.env.flush_all()
        return super()._search(domain, offset=offset, limit=limit, order=order)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ml.id AS id,
                    m.date AS date,
                    ml.product_id AS product_id,
                    pt.categ_id AS categ_id,
                    ml.product_uom_id AS uom_id,
                    ml.quantity_product_uom AS quantity,
                    ml.quantity_product_uom * COALESCE(ml.mgs_unit_cost, 0.0) AS cost,
                    CASE
                        WHEN m.mgs_event_id IS NOT NULL THEN 'event'
                        WHEN bc.id IS NOT NULL THEN 'bouquet'
                        ELSE 'pos'
                    END AS origin,
                    COALESCE(po.partner_id, ev.partner_id) AS partner_id,
                    pol.order_id AS pos_order_id,
                    m.mgs_event_id AS event_id,
                    m.company_id AS company_id
                FROM stock_move_line ml
                JOIN stock_move m ON m.id = ml.move_id
                JOIN stock_location dest ON dest.id = ml.location_dest_id
                JOIN product_product pp ON pp.id = ml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN pos_order_line pol ON pol.id = m.mgs_pos_line_id
                LEFT JOIN pos_order po ON po.id = pol.order_id
                -- bc.product_id = ml.product_id, no solo bc.line_id = pol.id:
                -- un ramo con varios materiales tiene varias filas de
                -- mgs_bouquet_component con el MISMO line_id (una por
                -- producto). Sin la condición del producto, cada movimiento
                -- del ramo se emparejaría con TODOS sus componentes a la vez
                -- y se contaría de más.
                LEFT JOIN mgs_bouquet_component bc
                       ON bc.line_id = pol.id AND bc.product_id = ml.product_id
                LEFT JOIN mgs_event ev ON ev.id = m.mgs_event_id
                WHERE m.state = 'done' AND dest.usage = 'customer'
            )
        """ % self._table)
