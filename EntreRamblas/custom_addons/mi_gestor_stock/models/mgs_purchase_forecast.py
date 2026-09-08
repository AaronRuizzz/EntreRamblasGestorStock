# -*- coding: utf-8 -*-
"""Previsión de compra para las fechas fuertes.

Sin esto, "cuánto pedir para San Valentín" era una corazonada: el ranking de
ventas mostraba «Ramo a medida: 40 unidades», no «480 tallos de rosa», así que
no servía para calcular una compra. Ahora que mgs.flower.consumption sabe el
consumo real hasta la flor (ver mgs_consumption.py), esta previsión mira el
mismo periodo de años anteriores, propone el máximo histórico con un margen de
seguridad, y le resta lo que ya hay en la tienda sin caducar.

Es una PROPUESTA, no una orden: "Crear pedido" solo rellena un
mgs.purchase.order en borrador, que la propietaria revisa y confirma como
cualquier otro.
"""
from datetime import date, datetime, time, timedelta

import pytz

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError

from .mgs_permissions import require_manager

CAMPAIGNS = [
    ("valentine", "San Valentín (14 de febrero)"),
    ("mothers_day", "Día de la Madre (primer domingo de mayo)"),
    ("all_saints", "Todos los Santos (1 de noviembre)"),
    ("custom", "Fechas libres"),
]
# Días de compra ANTES de la fecha señalada: es cuando de verdad se vende.
CAMPAIGN_WINDOW_DAYS = 7


class MgsPurchaseForecast(models.TransientModel):
    _name = "mgs.purchase.forecast"
    _description = "Previsión de compra por campaña"

    campaign = fields.Selection(CAMPAIGNS, required=True, default="valentine")
    years_back = fields.Integer("Años hacia atrás", default=2, required=True)
    safety_factor = fields.Float(
        "Margen de seguridad", default=1.15, required=True, digits=(4, 2),
        help="Se multiplica el máximo histórico por este factor antes de "
             "restarle el stock. 1.15 = un 15 % más, por si se vende mejor "
             "que en años anteriores.")
    date_from = fields.Date("Desde (fechas libres)")
    date_to = fields.Date("Hasta (fechas libres)")
    line_ids = fields.One2many("mgs.purchase.forecast.line", "forecast_id", readonly=True)
    has_history = fields.Boolean(readonly=True)
    years_used = fields.Char(readonly=True)

    def _mgs_campaign_window(self, year):
        """(fecha_desde, fecha_hasta) del año dado para la campaña elegida,
        contando los CAMPAIGN_WINDOW_DAYS anteriores a la fecha señalada."""
        self.ensure_one()
        if self.campaign == "valentine":
            end = date(year, 2, 14)
        elif self.campaign == "mothers_day":
            # Primer domingo de mayo: weekday() da lunes=0 ... domingo=6.
            first = date(year, 5, 1)
            end = first + timedelta(days=(6 - first.weekday()) % 7)
        elif self.campaign == "all_saints":
            end = date(year, 11, 1)
        else:
            if not self.date_from or not self.date_to or self.date_from > self.date_to:
                raise UserError(_("Indica las dos fechas, la inicial antes que la final."))
            return self.date_from, self.date_to
        return end - timedelta(days=CAMPAIGN_WINDOW_DAYS), end

    def _mgs_madrid_range(self, day_from, day_to):
        zone = pytz.timezone("Europe/Madrid")
        start = zone.localize(datetime.combine(day_from, time.min)).astimezone(pytz.UTC).replace(tzinfo=None)
        end = zone.localize(datetime.combine(day_to, time.max)).astimezone(pytz.UTC).replace(tzinfo=None)
        return start, end

    def _mgs_usual_supplier(self, product):
        """El proveedor que más veces ha traído este producto, según las
        partidas ya recibidas (stock.lot.mgs_supplier_id). Sin garantías: es
        una sugerencia, no una decisión — la propietaria puede cambiarla."""
        lots = self.env["stock.lot"].search([
            ("product_id", "=", product.id), ("mgs_supplier_id", "!=", False),
        ])
        if not lots:
            return self.env["res.partner"]
        counts = {}
        for lot in lots:
            counts[lot.mgs_supplier_id.id] = counts.get(lot.mgs_supplier_id.id, 0) + 1
        return self.env["res.partner"].browse(max(counts, key=counts.get))

    def action_compute(self):
        """Recalcula las líneas desde cero: mismo criterio que el cron de
        caducidad, siempre reemplaza, nunca acumula."""
        self.ensure_one()
        require_manager(self.env)
        self.line_ids.unlink()
        this_year = fields.Date.context_today(self).year
        years_back = max(1, self.years_back) if self.campaign != "custom" else 1
        by_product = {}  # product_id -> {year: qty}
        years_used = []
        for offset in range(1, years_back + 1):
            year = this_year - offset if self.campaign != "custom" else this_year
            day_from, day_to = self._mgs_campaign_window(year)
            start, end = self._mgs_madrid_range(day_from, day_to)
            rows = self.env["mgs.flower.consumption"].search([
                ("company_id", "=", self.env.company.id),
                ("date", ">=", start), ("date", "<=", end),
            ])
            if rows:
                years_used.append(year)
            for row in rows:
                by_year = by_product.setdefault(row.product_id.id, {})
                by_year[year] = by_year.get(year, 0.0) + row.quantity
            if self.campaign == "custom":
                break

        self.has_history = bool(years_used)
        self.years_used = ", ".join(str(y) for y in sorted(years_used)) or _("ninguno")
        now = fields.Datetime.now()
        rows_to_create = []
        for product_id, by_year in by_product.items():
            product = self.env["product.product"].browse(product_id)
            max_qty = max(by_year.values()) if by_year else 0.0
            quants = self.env["stock.quant"].search([
                ("product_id", "=", product_id), ("company_id", "=", self.env.company.id),
                ("location_id.usage", "=", "internal"), ("owner_id", "=", False),
            ])
            usable = sum(q.quantity - q.reserved_quantity for q in quants
                        if not q.lot_id.expiration_date or q.lot_id.expiration_date >= now)
            proposed = max(0.0, max_qty * self.safety_factor - usable)
            supplier = self._mgs_usual_supplier(product)
            rows_to_create.append({
                "forecast_id": self.id, "product_id": product_id,
                "history": " · ".join("%s: %g" % (y, by_year[y]) for y in sorted(by_year)),
                "max_qty": max_qty, "usable_qty": usable,
                "proposed_qty": proposed, "supplier_id": supplier.id if supplier else False,
            })
        self.env["mgs.purchase.forecast.line"].create(rows_to_create)
        return {
            "type": "ir.actions.act_window", "res_model": "mgs.purchase.forecast",
            "res_id": self.id, "view_mode": "form", "target": "current",
        }

    def action_create_purchase_order(self):
        self.ensure_one()
        require_manager(self.env)
        to_order = self.line_ids.filtered(lambda line: line.proposed_qty > 0)
        if not to_order:
            raise UserError(_("No hay nada que pedir: el stock ya cubre la previsión."))
        note = _("Generado desde la previsión de compra (%s).",
                 dict(self._fields["campaign"].selection).get(self.campaign))
        by_supplier = {}
        unassigned = self.env["mgs.purchase.forecast.line"]
        for line in to_order:
            if line.supplier_id:
                by_supplier.setdefault(line.supplier_id, self.env["mgs.purchase.forecast.line"])
                by_supplier[line.supplier_id] |= line
            else:
                unassigned |= line
        orders = self.env["mgs.purchase.order"]
        for supplier, lines in by_supplier.items():
            orders |= self.env["mgs.purchase.order"].create({
                "partner_id": supplier.id, "note": note,
                "line_ids": [Command.create({
                    "product_id": line.product_id.id, "quantity": line.proposed_qty,
                    "unit_cost": line.product_id.standard_price,
                }) for line in lines],
            })
        if not orders:
            raise UserError(_(
                "Ninguno de los productos con propuesta tiene un proveedor "
                "habitual todavía: recibe alguno de ellos al menos una vez, o "
                "crea el pedido a mano desde Pedidos a proveedor."))
        message = _("%(n)s pedido(s) creado(s) en borrador.", n=len(orders))
        if unassigned:
            message += " " + _(
                "Sin proveedor conocido, quedan fuera: %s.",
                ", ".join(unassigned.mapped("product_id.display_name")))
        return {
            "type": "ir.actions.act_window", "res_model": "mgs.purchase.order",
            "domain": [("id", "in", orders.ids)], "view_mode": "list,form",
            "target": "current",
            "context": {"mgs_forecast_message": message},
        }


class MgsPurchaseForecastLine(models.TransientModel):
    _name = "mgs.purchase.forecast.line"
    _description = "Partida de la previsión de compra"

    forecast_id = fields.Many2one("mgs.purchase.forecast", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", "Producto", required=True)
    history = fields.Char("Consumo en años anteriores")
    max_qty = fields.Float("Máximo histórico")
    usable_qty = fields.Float("Ya hay en la tienda (sin caducar)")
    proposed_qty = fields.Float("Propuesta de compra")
    supplier_id = fields.Many2one("res.partner", "Proveedor habitual")
