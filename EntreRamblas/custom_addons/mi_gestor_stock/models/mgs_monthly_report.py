# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

# Estados de un pedido de TPV que cuentan como venta real.
SOLD_STATES = ("paid", "done", "invoiced")


class MgsMonthlyReport(models.TransientModel):
    """Asistente del informe mensual en PDF: ventas, stock restante y balance."""
    _name = "mgs.monthly.report"
    _description = "Informe mensual"

    date_from = fields.Date("Desde", required=True, default=lambda s: s._default_from())
    date_to = fields.Date("Hasta", required=True, default=lambda s: s._default_to())

    @api.model
    def _default_from(self):
        return fields.Date.context_today(self).replace(day=1)

    @api.model
    def _default_to(self):
        first = fields.Date.context_today(self).replace(day=1)
        return first + relativedelta(months=1, days=-1)

    def action_print(self):
        self.ensure_one()
        return self.env.ref("mi_gestor_stock.action_report_mgs_monthly").report_action(self)

    # ------------------------------------------------------------------
    # Datos del informe (lo llama la plantilla QWeb)
    # ------------------------------------------------------------------
    def mgs_get_report_data(self):
        self.ensure_one()
        lines = self.env["pos.order.line"].search([
            ("order_id.date_order", ">=", fields.Datetime.to_datetime(self.date_from)),
            ("order_id.date_order", "<=", fields.Datetime.to_datetime(self.date_to).replace(
                hour=23, minute=59, second=59)),
            ("order_id.state", "in", SOLD_STATES),
        ])

        # --- Ventas agregadas por producto ---
        sold = {}
        for line in lines:
            tmpl = line.product_id.product_tmpl_id
            entry = sold.setdefault(tmpl.id, {
                "name": tmpl.name,
                "qty": 0.0,
                "revenue": 0.0,
                "cost": 0.0,
            })
            entry["qty"] += line.qty
            entry["revenue"] += line.price_subtotal_incl
            entry["cost"] += line.qty * tmpl.standard_price

        sold_rows = sorted(sold.values(), key=lambda r: r["revenue"], reverse=True)
        total_revenue = sum(r["revenue"] for r in sold_rows)
        total_cost_sold = sum(r["cost"] for r in sold_rows)
        total_qty_sold = sum(r["qty"] for r in sold_rows)

        # --- Entradas de mercancía (gasto de reposición) del periodo ---
        moves = self.env["stock.move"].search([
            ("state", "=", "done"),
            ("date", ">=", fields.Datetime.to_datetime(self.date_from)),
            ("date", "<=", fields.Datetime.to_datetime(self.date_to).replace(
                hour=23, minute=59, second=59)),
            ("location_id.usage", "in", ("supplier", "inventory")),
            ("location_dest_id.usage", "=", "internal"),
        ])
        purchases = 0.0
        purchased_qty = 0.0
        for move in moves:
            purchases += move.quantity * move.product_id.product_tmpl_id.standard_price
            purchased_qty += move.quantity

        # --- Stock restante ---
        products = self.env["product.template"].search([("is_storable", "=", True)])
        stock_rows = []
        stock_value = 0.0
        for tmpl in products.sorted(key=lambda p: p.name or ""):
            qty = tmpl.qty_available
            value = qty * tmpl.standard_price
            stock_value += value
            if qty:
                stock_rows.append({
                    "name": tmpl.name,
                    "qty": qty,
                    "uom": tmpl.uom_id.name,
                    "value": value,
                    "expiry": tmpl.mgs_expiry_date,
                })

        return {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "currency": self.env.company.currency_id,
            "sold_rows": sold_rows,
            "total_qty_sold": total_qty_sold,
            "total_revenue": total_revenue,
            "total_cost_sold": total_cost_sold,
            "gross_profit": total_revenue - total_cost_sold,
            "purchases": purchases,
            "purchased_qty": purchased_qty,
            "balance": total_revenue - purchases,
            "stock_rows": stock_rows,
            "stock_value": stock_value,
        }
