# -*- coding: utf-8 -*-
"""Entradas y salidas: un único listado de movimientos de stock ya
confirmados, para que la dueña pueda mirar "¿qué ha entrado y salido de
tal producto, y por qué?" sin abrir cinco pantallas distintas.

Igual que `mgs.flower.consumption` (ver ese fichero para la explicación
larga de por qué una vista SQL y no un modelo normal), esto NO crea ningún
registro nuevo: lee `stock_move_line`/`stock_move`/`stock_scrap` ya
confirmados y los une en una sola tabla de solo lectura. No hay libro de
movimientos paralelo, ni se duplican los componentes de un ramo (el mismo
cuidado de `mgs_bouquet_component` que ya tiene `mgs.flower.consumption`).

Cinco motivos, cuatro consultas UNION ALL:
  1. Recepción   → mercancía que entra de un proveedor.
  2. Venta       → lo que sale hacia el cliente (suelto, ramo o evento
                   consumible); reutiliza el mismo criterio que
                   `mgs.flower.consumption` para no duplicar ramo+componentes.
  3. Merma       → lo que se tira, con su motivo concreto (deterioro,
                   caducidad, rotura, devolución ya deteriorada).
  4. Devolución  → lo que vuelve de una venta (recuperable).
  5. Evento      → materiales de alquiler que van y vuelven de la ubicación
                   de tránsito de eventos (lo consumible de un evento ya
                   sale por la rama de "venta", con motivo 'event').
"""
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models, tools

from .mgs_permissions import is_manager, require_operator

MADRID = pytz.timezone("Europe/Madrid")


class MgsStockLedger(models.Model):
    _name = "mgs.stock.ledger"
    _description = "Entradas y salidas de stock (solo lectura)"
    _auto = False
    _order = "date desc, id desc"

    date = fields.Datetime(readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    categ_id = fields.Many2one("product.category", string="Categoría", readonly=True)
    uom_id = fields.Many2one("uom.uom", string="Unidad", readonly=True)
    direction = fields.Selection([("in", "Entrada"), ("out", "Salida")], readonly=True)
    motivo = fields.Selection([
        ("reception", "Recepción"),
        ("pos", "Venta suelta"),
        ("bouquet", "Componente de ramo"),
        ("event", "Evento o encargo"),
        ("scrap_deterioration", "Merma: deterioro"),
        ("scrap_expiry", "Merma: caducidad"),
        ("scrap_breakage", "Merma: rotura"),
        ("return", "Devolución"),
    ], readonly=True)
    quantity = fields.Float(readonly=True)
    cost = fields.Float(readonly=True, groups="mi_gestor_stock.group_mgs_manager")
    origin_document = fields.Char("Documento de origen", readonly=True)
    pos_order_id = fields.Many2one("pos.order", string="Venta", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    def _search(self, domain, offset=0, limit=None, order=None):
        # Mismo motivo que en mgs.flower.consumption: es una vista SQL sobre
        # otras tablas, así que hay que forzar el volcado de lo pendiente de
        # escribir en la MISMA transacción antes de preguntar.
        self.env.flush_all()
        return super()._search(domain, offset=offset, limit=limit, order=order)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                -- 1) Recepciones: de un proveedor a stock interno.
                SELECT
                    ml.id AS id, m.date AS date, ml.product_id AS product_id,
                    pt.categ_id AS categ_id, ml.product_uom_id AS uom_id,
                    'in' AS direction, 'reception' AS motivo,
                    ml.quantity_product_uom AS quantity,
                    ml.quantity_product_uom * COALESCE(ml.mgs_unit_cost, 0.0) AS cost,
                    COALESCE(pk.origin, '') AS origin_document,
                    NULL::int AS pos_order_id, m.company_id AS company_id
                FROM stock_move_line ml
                JOIN stock_move m ON m.id = ml.move_id
                JOIN stock_location src ON src.id = ml.location_id
                JOIN stock_location dest ON dest.id = ml.location_dest_id
                JOIN product_product pp ON pp.id = ml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN stock_picking pk ON pk.id = ml.picking_id
                WHERE m.state = 'done' AND src.usage = 'supplier' AND dest.usage = 'internal'

                UNION ALL

                -- 2) Ventas: a cliente, distinguiendo suelto/ramo/evento
                --    exactamente como mgs.flower.consumption (mismo JOIN de
                --    mgs_bouquet_component, mismo cuidado de no contar de más).
                SELECT
                    ml.id AS id, m.date AS date, ml.product_id AS product_id,
                    pt.categ_id AS categ_id, ml.product_uom_id AS uom_id,
                    'out' AS direction,
                    CASE
                        WHEN m.mgs_event_id IS NOT NULL THEN 'event'
                        WHEN bc.id IS NOT NULL THEN 'bouquet'
                        ELSE 'pos'
                    END AS motivo,
                    ml.quantity_product_uom AS quantity,
                    ml.quantity_product_uom * COALESCE(ml.mgs_unit_cost, 0.0) AS cost,
                    COALESCE(po.pos_reference, po.name, ev.name, '') AS origin_document,
                    pol.order_id AS pos_order_id, m.company_id AS company_id
                FROM stock_move_line ml
                JOIN stock_move m ON m.id = ml.move_id
                JOIN stock_location dest ON dest.id = ml.location_dest_id
                JOIN product_product pp ON pp.id = ml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN pos_order_line pol ON pol.id = m.mgs_pos_line_id
                LEFT JOIN pos_order po ON po.id = pol.order_id
                LEFT JOIN mgs_bouquet_component bc ON bc.line_id = pol.id AND bc.product_id = ml.product_id
                LEFT JOIN mgs_event ev ON ev.id = m.mgs_event_id
                WHERE m.state = 'done' AND dest.usage = 'customer'

                UNION ALL

                -- 3) Mermas: motivo concreto de stock.scrap.mgs_reason.
                SELECT
                    ml.id AS id, m.date AS date, ml.product_id AS product_id,
                    pt.categ_id AS categ_id, ml.product_uom_id AS uom_id,
                    'out' AS direction,
                    CASE sc.mgs_reason
                        WHEN 'expiry' THEN 'scrap_expiry'
                        WHEN 'breakage' THEN 'scrap_breakage'
                        ELSE 'scrap_deterioration'
                    END AS motivo,
                    ml.quantity_product_uom AS quantity,
                    ml.quantity_product_uom * COALESCE(ml.mgs_unit_cost, 0.0) AS cost,
                    COALESCE(sc.name, '') AS origin_document,
                    NULL::int AS pos_order_id, m.company_id AS company_id
                FROM stock_move_line ml
                JOIN stock_move m ON m.id = ml.move_id
                JOIN stock_scrap sc ON sc.id = m.scrap_id
                JOIN product_product pp ON pp.id = ml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE m.state = 'done' AND sc.mgs_reason != 'return'

                UNION ALL

                -- 4) Devoluciones de venta (recuperable): vuelven a stock
                --    interno enlazadas a la línea de movimiento original
                --    (mgs_return_origin_id). Si además está marcada como
                --    deteriorada, la rama 3 ya añade su propia salida por
                --    merma con motivo 'return': aquí se ve la entrada Y la
                --    salida, como dos movimientos reales que son.
                SELECT
                    ml.id AS id, m.date AS date, ml.product_id AS product_id,
                    pt.categ_id AS categ_id, ml.product_uom_id AS uom_id,
                    'in' AS direction, 'return' AS motivo,
                    ml.quantity_product_uom AS quantity,
                    ml.quantity_product_uom * COALESCE(ml.mgs_unit_cost, 0.0) AS cost,
                    COALESCE(po.pos_reference, po.name, '') AS origin_document,
                    pol.order_id AS pos_order_id, m.company_id AS company_id
                FROM stock_move_line ml
                JOIN stock_move m ON m.id = ml.move_id
                JOIN product_product pp ON pp.id = ml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN pos_order_line pol ON pol.id = m.mgs_pos_line_id
                LEFT JOIN pos_order po ON po.id = pol.order_id
                WHERE m.state = 'done' AND ml.mgs_return_origin_id IS NOT NULL

                UNION ALL

                -- 5) Movimientos de evento que no son venta a cliente (ida y
                --    vuelta del material de alquiler con la ubicación de
                --    tránsito): lo consumible del evento ya sale por la
                --    rama 2 con motivo 'event', así que aquí solo lo que NO
                --    va a "cliente" para no contarlo dos veces.
                SELECT
                    ml.id AS id, m.date AS date, ml.product_id AS product_id,
                    pt.categ_id AS categ_id, ml.product_uom_id AS uom_id,
                    CASE WHEN dest.usage = 'internal' THEN 'in' ELSE 'out' END AS direction,
                    'event' AS motivo,
                    ml.quantity_product_uom AS quantity,
                    ml.quantity_product_uom * COALESCE(ml.mgs_unit_cost, 0.0) AS cost,
                    COALESCE(ev.name, '') AS origin_document,
                    NULL::int AS pos_order_id, m.company_id AS company_id
                FROM stock_move_line ml
                JOIN stock_move m ON m.id = ml.move_id
                JOIN stock_location dest ON dest.id = ml.location_dest_id
                JOIN product_product pp ON pp.id = ml.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN mgs_event ev ON ev.id = m.mgs_event_id
                WHERE m.state = 'done' AND m.mgs_event_id IS NOT NULL AND dest.usage != 'customer'
            )
        """ % self._table)

    @api.model
    def mgs_ledger_data(self, direction=None, product_query=None, date_from=None, date_to=None, limit=500):
        """Datos ya listos para pintar la pantalla «Entradas y salidas»:
        filtra por dirección/producto/rango de fechas (mes actual en zona
        Europe/Madrid por defecto, igual que el resto de informes de la
        tienda) y devuelve las filas con la etiqueta de motivo ya traducida
        y el coste quitado si quien pregunta no es responsable de tienda."""
        require_operator(self.env)
        today = datetime.now(MADRID).date()
        if date_from:
            date_from = fields.Date.from_string(date_from)
        else:
            date_from = today.replace(day=1)
        if date_to:
            date_to = fields.Date.from_string(date_to)
        else:
            next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
            date_to = next_month - timedelta(days=1)
        start = MADRID.localize(datetime.combine(date_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = MADRID.localize(datetime.combine(date_to, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
        domain = [
            ("company_id", "=", self.env.company.id),
            ("date", ">=", start), ("date", "<=", end),
        ]
        if direction in ("in", "out"):
            domain.append(("direction", "=", direction))
        if product_query:
            products = self.env["product.product"].search([("name", "ilike", product_query)])
            domain.append(("product_id", "in", products.ids))
        can_see_cost = is_manager(self.env)
        fields_to_read = ["date", "product_id", "categ_id", "uom_id", "direction",
                          "motivo", "quantity", "origin_document"]
        if can_see_cost:
            fields_to_read.append("cost")
        records = self.search(domain, limit=limit, order=self._order)
        rows = records.read(fields_to_read)
        motivo_labels = dict(self._fields["motivo"]._description_selection(self.env))
        for row in rows:
            row["motivo_label"] = motivo_labels.get(row["motivo"], row["motivo"] or "")
            when = row["date"]
            if when:
                local = fields.Datetime.context_timestamp(self, when)
                row["date"] = local.strftime("%d/%m/%Y %H:%M")
            row["product_name"] = row["product_id"][1] if row["product_id"] else ""
            row["categ_name"] = row["categ_id"][1] if row["categ_id"] else ""
            row["uom_name"] = row["uom_id"][1] if row["uom_id"] else ""
        return {
            "rows": rows, "can_see_cost": can_see_cost, "truncated": len(rows) >= limit,
            "date_from": fields.Date.to_string(date_from), "date_to": fields.Date.to_string(date_to),
        }
