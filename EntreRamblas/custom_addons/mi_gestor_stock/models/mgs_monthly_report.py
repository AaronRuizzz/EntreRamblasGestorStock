# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
import base64
import csv
import io
import pytz
import zipfile

from odoo import api, fields, models, _
from .mgs_permissions import require_manager, madrid_day_range

# Estados de un pedido de TPV que cuentan como venta real.
SOLD_STATES = ("paid", "done", "invoiced")


class MgsMonthlyReport(models.TransientModel):
    """Asistente del informe mensual en PDF: ventas, stock restante y balance."""
    _name = "mgs.monthly.report"
    _description = "Informe mensual"

    date_from = fields.Date("Desde", required=True, default=lambda s: s._default_from())
    date_to = fields.Date("Hasta", required=True, default=lambda s: s._default_to())
    category_id = fields.Many2one("product.category", "Categoría")
    csv_file = fields.Binary(readonly=True, attachment=False)
    csv_filename = fields.Char(readonly=True)
    export_file = fields.Binary(readonly=True, attachment=False)
    export_filename = fields.Char(readonly=True)

    def action_export_all_csv(self):
        self.ensure_one()
        data = self.mgs_get_report_data()
        output = io.BytesIO()

        def safe(value):
            # Solo el texto puede convertirse en fórmula; conservar números negativos.
            if isinstance(value, str) and value.lstrip()[:1] in ('=', '+', '-', '@'):
                return "'" + value
            if isinstance(value, str) and value[:1] in ('\t', '\r', '\n'):
                return "'" + value
            return value

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            def table(name, header, rows):
                buffer = io.StringIO(newline='')
                writer = csv.writer(buffer, delimiter=';')
                writer.writerow(header)
                writer.writerows([safe(value) for value in row] for row in rows)
                archive.writestr(name + '.csv', buffer.getvalue().encode('utf-8-sig'))

            metrics = [
                ('Ventas antes de devoluciones, con impuestos', 'gross_sales_including_tax'),
                ('Devoluciones con impuestos', 'refunds_including_tax'),
                ('Ventas netas sin impuestos', 'total_revenue'), ('Impuestos netos', 'taxes'),
                ('Ventas netas con impuestos', 'sales_including_tax'),
                ('Coste histórico vendido neto', 'total_cost_sold'), ('Margen bruto', 'gross_profit'),
                ('Coste de mermas', 'scrap_cost'), ('Margen después de mermas', 'margin_after_scrap'),
                ('Tickets con venta', 'sale_ticket_count'), ('Tickets con devolución', 'refund_ticket_count'),
                ('Ticket medio de venta con impuestos', 'average_sale_ticket'),
                ('Entradas de proveedor a coste', 'purchases'),
                ('Valor de stock actual', 'stock_value'),
                ('Valor de stock vendible', 'stock_value_usable'),
                ('Valor de stock caducado', 'stock_value_expired'),
                ('Registros sin coste histórico', 'missing_costs'),
                ('Coste histórico del consumo de flor (informativo)', 'consumption_cost'),
            ]
            if data['payments_available']:
                metrics += [('Cobros netos', 'payments_net'), ('Cuenta cliente neta no cobrada', 'payments_deferred_net')]
            table('resumen', ['Concepto', 'Valor'], [
                ['Desde', self.date_from], ['Hasta', self.date_to], ['Zona horaria', 'Europe/Madrid'],
                ['Moneda', data['currency'].name], ['Categoría', data['category'] or 'Todas'],
                ['Stock consultado (UTC)', fields.Datetime.now()],
                ['Cobros disponibles', 'Sí' if data['payments_available'] else 'No: filtro de categoría'],
            ] + [[label, data[key]] for label, key in metrics])
            table('ventas', ['Producto', 'Unidades netas', 'Ventas sin impuestos', 'Coste histórico', 'Margen bruto'],
                  [[r['name'], r['qty'], r['revenue'], r['cost'], r['revenue'] - r['cost']] for r in data['sold_rows']])
            table('ventas_diarias', ['Fecha Madrid', 'Ventas sin impuestos', 'Impuestos', 'Coste histórico', 'Margen bruto'],
                  [[r['date'], r['revenue'], r['taxes'], r['cost'], r['revenue'] - r['cost']] for r in data['daily_rows']])
            table('mermas',
                  ['Fecha', 'Referencia', 'Producto', 'Partida', 'Motivo', 'Cantidad', 'Unidad',
                   'Registrado por', 'Coste histórico'],
                  [[r[k] for k in ('date', 'reference', 'product', 'lot', 'reason', 'quantity', 'uom',
                                   'recorded_by', 'cost')] for r in data['scrap_rows']])
            table('stock_actual', ['Producto', 'Cantidad', 'Unidad', 'Valor'],
                  [[r[k] for k in ('name', 'qty', 'uom', 'value')] for r in data['stock_rows']])
            table('consumo_flor', ['Producto', 'Cantidad consumida', 'Unidad', 'Coste histórico'],
                  [[r[k] for k in ('name', 'qty', 'uom', 'cost')] for r in data['consumption_rows']])
            if data['payments_available']:
                table('cobros', ['Método', 'Entradas', 'Salidas (cambio y reembolso)', 'Neto', 'Cuenta cliente no cobrada'],
                      [[r['name'], r['received'], r['returned'], r['received'] - r['returned'],
                        'Sí' if r['deferred'] else 'No'] for r in data['payment_rows']])
            archive.writestr('LEEME.txt', (
                'CSV UTF-8 con BOM, separador punto y coma, decimales con punto.\n'
                'Importa los CSV eligiendo estos ajustes en tu hoja de cálculo.\n'
                'Ventas y mermas: periodo inclusivo Europe/Madrid. Cobros: fecha del pago.\n'
                'El stock es actual, no el stock al final del periodo.\n'
                'Con categoría seleccionada se omiten cobros: los pagos mixtos no tienen reparto exacto por categoría.\n'
                'La cuenta de cliente se separa de los cobros efectivos.\n'
                'Los textos que podrían interpretarse como fórmulas llevan un apóstrofo inicial.\n'
            ).encode('utf-8'))
        self.write({'export_file': base64.b64encode(output.getvalue()),
                    'export_filename': 'estadisticas-%s-%s.zip' % (self.date_from, self.date_to)})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/web/content/mgs.monthly.report/%s/export_file/%s?download=true' % (self.id, self.export_filename)}

    def _mgs_period(self):
        self.ensure_one()
        return madrid_day_range(self.env, self.date_from, self.date_to)

    def action_export_csv(self):
        self.ensure_one()
        data = self.mgs_get_report_data()
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["Producto", "Unidades netas", "Ventas sin impuestos", "Coste histórico", "Margen bruto"])
        for row in data["sold_rows"]:
            name = row["name"]
            if name and name[0] in "=+-@\t\r\n":
                name = "'" + name
            writer.writerow([name, row["qty"], row["revenue"], row["cost"], row["revenue"] - row["cost"]])
        self.write({"csv_file": base64.b64encode(output.getvalue().encode("utf-8-sig")),
                    "csv_filename": "ventas-%s-%s.csv" % (self.date_from, self.date_to)})
        return {"type": "ir.actions.act_url", "target": "download",
                "url": "/web/content/mgs.monthly.report/%s/csv_file/%s?download=true" % (self.id, self.csv_filename)}

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
        require_manager(self.env)
        self.ensure_one()
        start, end = self._mgs_period()
        category_domain = [("product_id.categ_id", "child_of", self.category_id.id)] if self.category_id else []
        lines = self.env["pos.order.line"].search(category_domain + [
            ("company_id", "=", self.env.company.id),
            ("order_id.date_order", ">=", start),
            ("order_id.date_order", "<", end),
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
            entry["revenue"] += line.price_subtotal
            entry["cost"] += line.total_cost

        sold_rows = sorted(sold.values(), key=lambda r: r["revenue"], reverse=True)
        total_revenue = sum(r["revenue"] for r in sold_rows)
        total_cost_sold = sum(r["cost"] for r in sold_rows)
        total_qty_sold = sum(r["qty"] for r in sold_rows)
        positive = lines.filtered(lambda line: line.qty > 0)
        negative = lines.filtered(lambda line: line.qty < 0)
        sale_ticket_count = len(positive.order_id)
        gross_sales = sum(positive.mapped("price_subtotal_incl"))
        refunds = -sum(negative.mapped("price_subtotal_incl"))
        daily = {}
        madrid = pytz.timezone("Europe/Madrid")
        for line in lines:
            day = pytz.UTC.localize(line.order_id.date_order).astimezone(madrid).date()
            row = daily.setdefault(day, {"date": day, "revenue": 0.0, "cost": 0.0, "taxes": 0.0})
            row["revenue"] += line.price_subtotal
            row["cost"] += line.total_cost
            row["taxes"] += line.price_subtotal_incl - line.price_subtotal

        scraps = self.env["stock.scrap"].search(category_domain + [
            ("company_id", "=", self.env.company.id), ("state", "=", "done"),
            ("date_done", ">=", start), ("date_done", "<", end),
        ])
        reasons = dict(self.env["stock.scrap"]._fields["mgs_reason"]._description_selection(self.env))
        scrap_rows = []
        for scrap in scraps.sorted("date_done"):
            move_lines = scrap.move_ids.move_line_ids
            done = fields.Datetime.context_timestamp(self, scrap.date_done) if scrap.date_done else False
            scrap_rows.append({"product": scrap.product_id.display_name,
                "date": fields.Date.to_string(done.date()) if done else "",
                "reference": scrap.name or "",
                "lot": scrap.lot_id.name or "", "reason": reasons.get(scrap.mgs_reason, ""),
                "quantity": sum(move_lines.mapped("quantity_product_uom")),
                "uom": scrap.product_id.uom_id.name,
                "recorded_by": scrap.mgs_validated_by.name or "",
                "cost": sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in move_lines)})
        scrap_cost = sum(row["cost"] for row in scrap_rows)

        # Un cobro mixto no se puede atribuir exactamente a categorías.
        # Se muestra solo con el informe de todas las categorías y por fecha de pago.
        payment_rows = []
        if not self.category_id:
            payments = self.env["pos.payment"].search([
                ("pos_order_id.company_id", "=", self.env.company.id),
                ("pos_order_id.state", "in", SOLD_STATES),
                ("payment_date", ">=", start), ("payment_date", "<", end),
            ])
            grouped = {}
            for payment in payments:
                method = payment.payment_method_id
                deferred = method.type == "pay_later"
                row = grouped.setdefault(method.id, {"name": method.name + (_(" (cuenta cliente, no cobrado)") if deferred else ""),
                    "received": 0.0, "returned": 0.0, "deferred": deferred})
                row["received" if payment.amount >= 0 else "returned"] += abs(payment.amount)
            payment_rows = sorted(grouped.values(), key=lambda row: row["name"])

        # --- Entradas de mercancía (gasto de reposición) del periodo ---
        moves = self.env["stock.move"].search(category_domain + [
            ("company_id", "=", self.env.company.id),
            ("state", "=", "done"),
            ("date", ">=", start),
            ("date", "<", end),
            ("location_id.usage", "=", "supplier"),
            ("location_dest_id.usage", "=", "internal"),
        ])
        purchases = 0.0
        purchased_qty = 0.0
        for move in moves:
            purchases += sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in move.move_line_ids)
            purchased_qty += sum(move.move_line_ids.mapped("quantity_product_uom"))

        # --- Stock restante ---
        products = self.env["product.template"].search([("is_storable", "=", True)] +
            ([("categ_id", "child_of", self.category_id.id)] if self.category_id else []))
        stock_rows = []
        stock_value = 0.0
        stock_value_expired = 0.0
        # Mismo criterio de "caducado" que usa el TPV para no ofrecerlo en
        # venta (mgs_pos_stock.py): expiration_date < ahora, sin ajuste de
        # huso horario. Así el valor de aquí y lo que de verdad se puede
        # vender coinciden.
        now = fields.Datetime.now()
        for tmpl in products.sorted(key=lambda p: p.name or ""):
            quants = self.env["stock.quant"].search([
                ("product_id.product_tmpl_id", "=", tmpl.id),
                ("company_id", "=", self.env.company.id), ("location_id.usage", "=", "internal"),
                ("owner_id", "=", False),
            ])
            qty = sum(quants.mapped("quantity"))
            value = sum(q.quantity * (q.lot_id.mgs_unit_cost if q.lot_id.mgs_cost_recorded
                                     else q.product_id.standard_price) for q in quants)
            expired_value = sum(
                q.quantity * (q.lot_id.mgs_unit_cost if q.lot_id.mgs_cost_recorded
                             else q.product_id.standard_price)
                for q in quants if q.lot_id.expiration_date and q.lot_id.expiration_date < now)
            stock_value += value
            stock_value_expired += expired_value
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
            "category": self.category_id.display_name if self.category_id else False,
            "sale_ticket_count": sale_ticket_count,
            "refund_ticket_count": len(negative.order_id),
            "gross_sales_including_tax": gross_sales,
            "refunds_including_tax": refunds,
            "average_sale_ticket": gross_sales / sale_ticket_count if sale_ticket_count else 0.0,
            "daily_rows": [daily[day] for day in sorted(daily)],
            "scrap_rows": scrap_rows,
            "scrap_cost": scrap_cost,
            "margin_after_scrap": total_revenue - total_cost_sold - scrap_cost,
            "payment_rows": payment_rows,
            "payments_available": not self.category_id,
            "payments_net": sum(row["received"] - row["returned"] for row in payment_rows if not row["deferred"]),
            "payments_deferred_net": sum(row["received"] - row["returned"] for row in payment_rows if row["deferred"]),
            "sold_rows": sold_rows,
            "total_qty_sold": total_qty_sold,
            "total_revenue": total_revenue,
            "taxes": sum(line.price_subtotal_incl - line.price_subtotal for line in lines),
            "sales_including_tax": sum(lines.mapped("price_subtotal_incl")),
            "missing_costs": len(lines.filtered(lambda line: not line.is_total_cost_computed)) +
                len(moves.move_line_ids.filtered(lambda ml: not ml.mgs_cost_recorded)) +
                len(scraps.move_ids.move_line_ids.filtered(lambda ml: not ml.mgs_cost_recorded)),
            "total_cost_sold": total_cost_sold,
            "gross_profit": total_revenue - total_cost_sold,
            "purchases": purchases,
            "purchased_qty": purchased_qty,
            "balance": total_revenue - purchases,
            "stock_rows": stock_rows,
            "stock_value": stock_value,
            "stock_value_expired": stock_value_expired,
            "stock_value_usable": stock_value - stock_value_expired,
            **self._mgs_event_data(start, end),
            **self._mgs_consumption_data(start, end),
        }

    def _mgs_consumption_data(self, start, end):
        """Cuánta flor se ha consumido de verdad en el periodo, por producto,
        sobre mgs.flower.consumption (ver models/mgs_consumption.py).

        Es solo informativo: NO se suma a total_revenue ni a total_cost_sold.
        Ese coste ya está contado dentro de line.total_cost de la línea de
        venta (la del ramo, no la de sus flores); sumarlo aquí lo contaría
        dos veces. Mismo razonamiento que ya usa _mgs_event_data para no
        mezclar los eventos con las ventas de mostrador."""
        domain = [("company_id", "=", self.env.company.id),
                  ("date", ">=", start), ("date", "<", end)]
        if self.category_id:
            domain.append(("categ_id", "child_of", self.category_id.id))
        by_product = {}
        for row in self.env["mgs.flower.consumption"].search(domain):
            entry = by_product.setdefault(row.product_id.id, {
                "name": row.product_id.display_name, "qty": 0.0, "cost": 0.0,
                "uom": row.uom_id.name,
            })
            entry["qty"] += row.quantity
            entry["cost"] += row.cost
        consumption_rows = sorted(by_product.values(), key=lambda r: r["qty"], reverse=True)
        return {
            "consumption_rows": consumption_rows,
            "consumption_cost": sum(r["cost"] for r in consumption_rows),
        }

    def _mgs_event_data(self, start, end):
        """Eventos y encargos del periodo.

        El dinero de un evento NO pasa por la caja del TPV (se cobra por señal y
        cobro final, ver mgs_event.py), así que va en su propio apartado: sumarlo
        a las ventas de mostrador contaría dos veces las que sí pasan por caja y
        mezclaría cobros de fechas distintas. Las mermas del material roto sí
        aparecen ya en el apartado de mermas, porque son mermas de verdad.

        Se filtra por FECHA DEL EVENTO, no por fecha de cobro: es lo que la dueña
        busca cuando mira «qué eventos hubo en junio». Los cobros del periodo van
        aparte, porque una señal de marzo es dinero de marzo."""
        if self.category_id:
            # Un evento mezcla categorías; repartirlo sería inventar.
            return {"event_rows": [], "event_total": 0.0, "event_collected": 0.0,
                    "events_available": False, "event_pending_return": 0}
        # `event_date` es una fecha, no un instante: se compara con las fechas
        # del asistente (ambas incluidas), no con los límites UTC de _mgs_period,
        # que sirven para los campos de fecha y hora.
        events = self.env["mgs.event"].search([
            ("company_id", "=", self.env.company.id),
            ("state", "!=", "cancelled"),
            ("event_date", ">=", self.date_from),
            ("event_date", "<=", self.date_to),
        ], order="event_date")
        rows = [{
            "name": event.name,
            "partner": event.partner_id.display_name,
            "date": event.event_date,
            "state": dict(event._fields["state"].selection).get(event.state, event.state),
            "total": event.amount_total,
            "paid": event.amount_paid,
            "due": event.amount_due,
            "pending_return": event.pending_return,
        } for event in events]
        payments = self.env["mgs.event.payment"].search([
            ("company_id", "=", self.env.company.id),
            ("date", ">=", start), ("date", "<", end),
        ])
        # Los cobros hechos en caja («Cobrar en caja» del encargo) YA están en
        # las ventas de mostrador de arriba: se separan para que quede claro que
        # esa parte no se suma dos veces.
        collected_pos = sum(payments.filtered(
            lambda p: (p.note or "").startswith("Cobrado en caja")).mapped("amount"))
        return {
            "event_rows": rows,
            "event_total": sum(event.amount_total for event in events),
            "event_collected": sum(payments.mapped("amount")),
            "event_collected_pos": collected_pos,
            "events_available": True,
            "event_pending_return": sum(1 for event in events if event.pending_return),
        }
