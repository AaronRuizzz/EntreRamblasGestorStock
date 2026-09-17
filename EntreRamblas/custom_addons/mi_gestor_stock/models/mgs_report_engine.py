# -*- coding: utf-8 -*-
"""Motor de datos de los informes personalizados.

Funciones puras `(env, ...filtros) -> filas`, una por sección, más `build`,
que las combina según qué secciones tenga marcadas la plantilla
(`mgs.report.template`, ver models/mgs_report_template.py).

Deliberadamente NO reutiliza `mgs.monthly.report.mgs_get_report_data()`: ese
método solo admite una categoría, no tiene un punto de entrada parametrizado
y tiene su propia batería de pruebas de regresión (test_pos_stock.py,
test_consumption.py, test_event.py...) — tocarlo para añadir más filtros se
arriesgaba a romperlas. Aquí se repiten las mismas formas de consulta (mismos
estados de pedido, misma ventana horaria de Madrid vía `madrid_day_range`)
sin llamar al código legado, así ninguno de los dos puede romper al otro.
Ver test_report_engine.py::TestReportEngineMatchesLegacy para la
comprobación cruzada que vigila que no diverjan con el tiempo.
"""
from datetime import timedelta

import pytz
from odoo import _, fields

from .mgs_monthly_report import SOLD_STATES
from .mgs_permissions import madrid_day_range

MADRID = pytz.timezone("Europe/Madrid")


def _category_domain(category_ids, field="product_id.categ_id"):
    return [(field, "child_of", category_ids)] if category_ids else []


def _product_domain(product_ids, field="product_id"):
    return [(field, "in", product_ids)] if product_ids else []


# ----------------------------------------------------------------------
# Resumen
# ----------------------------------------------------------------------
def resumen(env, company, start, end, category_ids, product_ids):
    domain = _category_domain(category_ids) + _product_domain(product_ids) + [
        ("company_id", "=", company.id),
        ("order_id.date_order", ">=", start), ("order_id.date_order", "<", end),
        ("order_id.state", "in", SOLD_STATES),
    ]
    lines = env["pos.order.line"].search(domain)
    positive = lines.filtered(lambda line: line.qty > 0)
    negative = lines.filtered(lambda line: line.qty < 0)
    # Neto: cada línea de devolución tiene importe negativo, así que sumar
    # TODAS las líneas ya descuenta las devoluciones del periodo.
    total_revenue = sum(lines.mapped("price_subtotal"))
    total_cost_sold = sum(lines.mapped("total_cost"))
    gross_sales = sum(positive.mapped("price_subtotal_incl"))
    sale_ticket_count = len(positive.order_id)
    return {
        "sale_ticket_count": sale_ticket_count,
        "refund_ticket_count": len(negative.order_id),
        "gross_sales_including_tax": gross_sales,
        "refunds_including_tax": -sum(negative.mapped("price_subtotal_incl")),
        "total_revenue": total_revenue,
        "total_cost_sold": total_cost_sold,
        "gross_profit": total_revenue - total_cost_sold,
        "sales_including_tax": sum(lines.mapped("price_subtotal_incl")),
        "taxes": sum(lines.mapped("price_subtotal_incl")) - total_revenue,
        "average_sale_ticket": gross_sales / sale_ticket_count if sale_ticket_count else 0.0,
        "missing_costs": len(lines.filtered(lambda line: not line.is_total_cost_computed)),
    }


# ----------------------------------------------------------------------
# Agrupación compartida por ventas/devoluciones
# ----------------------------------------------------------------------
def _group_key(line, group_by):
    if group_by == "product":
        tmpl = line.product_id.product_tmpl_id
        return tmpl.id, tmpl.name
    if group_by == "category":
        categ = line.product_id.categ_id
        return categ.id, categ.display_name or _("Sin categoría")
    if group_by == "payment_method":
        methods = line.order_id.payment_ids.payment_method_id
        if len(methods) == 1:
            return methods.id, methods.name
        if len(methods) > 1:
            return "mixed", _("Mixto")
        return "none", _("Sin pago registrado")
    if group_by in ("day", "week", "month"):
        local_date = pytz.UTC.localize(line.order_id.date_order).astimezone(MADRID).date()
        if group_by == "day":
            return local_date.isoformat(), fields.Date.to_string(local_date)
        if group_by == "week":
            monday = local_date - timedelta(days=local_date.weekday())
            return monday.isoformat(), _("Semana del %s") % fields.Date.to_string(monday)
        month_start = local_date.replace(day=1)
        return month_start.isoformat(), fields.Date.to_string(month_start)
    return "all", _("Todo el periodo")


def _aggregate(lines, group_by):
    buckets = {}
    order = []
    for line in lines:
        key, label = _group_key(line, group_by)
        row = buckets.get(key)
        if row is None:
            row = {"key": key, "label": label, "qty": 0.0, "amount": 0.0,
                   "tax": 0.0, "cost": 0.0, "count": 0}
            buckets[key] = row
            order.append(key)
        row["qty"] += line.qty
        row["amount"] += line.price_subtotal
        row["tax"] += line.price_subtotal_incl - line.price_subtotal
        row["cost"] += line.total_cost
        row["count"] += 1
    return [buckets[key] for key in order]


def _order_rows(rows, order_by, key=lambda row: row.get("label") or ""):
    if order_by == "amount_asc":
        return sorted(rows, key=lambda row: row.get("amount", 0.0))
    if order_by == "amount_desc":
        return sorted(rows, key=lambda row: row.get("amount", 0.0), reverse=True)
    if order_by == "date_asc":
        return sorted(rows, key=key)
    return sorted(rows, key=key, reverse=True)  # date_desc, valor por defecto


# ----------------------------------------------------------------------
# Ventas / devoluciones
# ----------------------------------------------------------------------
def ventas(env, company, start, end, category_ids, product_ids, group_by, order_by):
    """Solo líneas vendidas (qty > 0): las devoluciones tienen su propia
    sección, sin netear entre sí, para que cada una se pueda auditar."""
    domain = _category_domain(category_ids) + _product_domain(product_ids) + [
        ("company_id", "=", company.id),
        ("order_id.date_order", ">=", start), ("order_id.date_order", "<", end),
        ("order_id.state", "in", SOLD_STATES), ("qty", ">", 0),
    ]
    lines = env["pos.order.line"].search(domain)
    return _order_rows(_aggregate(lines, group_by), order_by)


def devoluciones(env, company, start, end, category_ids, product_ids, order_by):
    """Una fila por línea de devolución (qty < 0), con el pedido original y el
    de la devolución enlazados: es la trazabilidad que pide el informe, y se
    perdería si se agregara por producto como en `ventas`."""
    domain = _category_domain(category_ids) + _product_domain(product_ids) + [
        ("company_id", "=", company.id),
        ("order_id.date_order", ">=", start), ("order_id.date_order", "<", end),
        ("order_id.state", "in", SOLD_STATES), ("qty", "<", 0),
    ]
    lines = env["pos.order.line"].search(domain)
    rows = [{
        "date": pytz.UTC.localize(line.order_id.date_order).astimezone(MADRID).date(),
        "original_order": line.refunded_orderline_id.order_id.name or "",
        "return_order": line.order_id.name or "",
        "product": line.product_id.display_name,
        "qty": -line.qty,
        "amount": -line.price_subtotal_incl,
        "user": line.order_id.user_id.name or "",
    } for line in lines]
    return _order_rows(rows, order_by, key=lambda row: row["date"])


# ----------------------------------------------------------------------
# Cobros
# ----------------------------------------------------------------------
def cobros(env, company, start, end, payment_method_ids, category_ids, product_ids):
    # Un cobro mixto no se puede atribuir exactamente a una categoría o
    # producto: igual que en el informe mensual, se omite entero con esos
    # filtros activos en vez de repartirlo a ojo.
    available = not (category_ids or product_ids)
    if not available:
        return [], False
    domain = [
        ("pos_order_id.company_id", "=", company.id),
        ("pos_order_id.state", "in", SOLD_STATES),
        ("payment_date", ">=", start), ("payment_date", "<", end),
    ]
    if payment_method_ids:
        domain.append(("payment_method_id", "in", payment_method_ids))
    grouped = {}
    for payment in env["pos.payment"].search(domain):
        method = payment.payment_method_id
        deferred = method.type == "pay_later"
        row = grouped.setdefault(method.id, {
            "name": method.name + (_(" (cuenta cliente, no cobrado)") if deferred else ""),
            "received": 0.0, "returned": 0.0, "deferred": deferred, "count": 0,
        })
        row["received" if payment.amount >= 0 else "returned"] += abs(payment.amount)
        row["count"] += 1
    return sorted(grouped.values(), key=lambda row: row["name"]), True


# ----------------------------------------------------------------------
# Mermas
# ----------------------------------------------------------------------
def mermas(env, company, start, end, category_ids, product_ids):
    domain = _category_domain(category_ids) + _product_domain(product_ids) + [
        ("company_id", "=", company.id), ("state", "=", "done"),
        ("date_done", ">=", start), ("date_done", "<", end),
    ]
    scraps = env["stock.scrap"].search(domain)
    reasons = dict(env["stock.scrap"]._fields["mgs_reason"]._description_selection(env))
    rows = []
    for scrap in scraps.sorted("date_done"):
        move_lines = scrap.move_ids.move_line_ids
        done = fields.Datetime.context_timestamp(env.user, scrap.date_done) if scrap.date_done else False
        rows.append({
            "date": fields.Date.to_string(done.date()) if done else "",
            "reference": scrap.name or "", "product": scrap.product_id.display_name,
            "lot": scrap.lot_id.name or "", "reason": reasons.get(scrap.mgs_reason, ""),
            "quantity": sum(move_lines.mapped("quantity_product_uom")),
            "uom": scrap.product_id.uom_id.name,
            "recorded_by": scrap.mgs_validated_by.name or "",
            "cost": sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in move_lines),
        })
    return rows


# ----------------------------------------------------------------------
# Stock
# ----------------------------------------------------------------------
def stock(env, company, category_ids, product_ids):
    domain = [("is_storable", "=", True)]
    if category_ids:
        domain.append(("categ_id", "child_of", category_ids))
    if product_ids:
        domain.append(("product_variant_ids", "in", product_ids))
    products = env["product.template"].search(domain)
    rows = []
    total_value = 0.0
    total_expired = 0.0
    now = fields.Datetime.now()
    for tmpl in products.sorted(key=lambda product: product.name or ""):
        quants = env["stock.quant"].search([
            ("product_id.product_tmpl_id", "=", tmpl.id),
            ("company_id", "=", company.id), ("location_id.usage", "=", "internal"),
            ("owner_id", "=", False),
        ])
        qty = sum(quants.mapped("quantity"))
        value = sum(quant.quantity * (quant.lot_id.mgs_unit_cost if quant.lot_id.mgs_cost_recorded
                                       else quant.product_id.standard_price) for quant in quants)
        expired_value = sum(
            quant.quantity * (quant.lot_id.mgs_unit_cost if quant.lot_id.mgs_cost_recorded
                              else quant.product_id.standard_price)
            for quant in quants if quant.lot_id.expiration_date and quant.lot_id.expiration_date < now)
        total_value += value
        total_expired += expired_value
        if qty:
            rows.append({"name": tmpl.name, "qty": qty, "uom": tmpl.uom_id.name,
                         "value": value, "expiry": tmpl.mgs_expiry_date})
    return rows, total_value, total_expired


# ----------------------------------------------------------------------
# Consumo de flor
# ----------------------------------------------------------------------
def consumo(env, company, start, end, category_ids, product_ids):
    domain = [("company_id", "=", company.id), ("date", ">=", start), ("date", "<", end)]
    if category_ids:
        domain.append(("categ_id", "child_of", category_ids))
    if product_ids:
        domain.append(("product_id", "in", product_ids))
    by_product = {}
    for row in env["mgs.flower.consumption"].search(domain):
        entry = by_product.setdefault(row.product_id.id, {
            "name": row.product_id.display_name, "qty": 0.0, "cost": 0.0, "uom": row.uom_id.name})
        entry["qty"] += row.quantity
        entry["cost"] += row.cost
    return sorted(by_product.values(), key=lambda row: row["qty"], reverse=True)


# ----------------------------------------------------------------------
# Eventos
# ----------------------------------------------------------------------
def eventos(env, company, date_from, date_to, start, end, category_ids, product_ids):
    if category_ids or product_ids:
        # Un evento mezcla categorías; repartirlo sería inventar (mismo
        # criterio que mgs.monthly.report._mgs_event_data).
        return {"rows": [], "total": 0.0, "collected": 0.0, "collected_pos": 0.0,
                "available": False, "pending_return": 0}
    events = env["mgs.event"].search([
        ("company_id", "=", company.id), ("state", "!=", "cancelled"),
        ("event_date", ">=", date_from), ("event_date", "<=", date_to),
    ], order="event_date")
    rows = [{
        "name": event.name, "partner": event.partner_id.display_name, "date": event.event_date,
        "state": dict(event._fields["state"].selection).get(event.state, event.state),
        "total": event.amount_total, "paid": event.amount_paid, "due": event.amount_due,
        "pending_return": event.pending_return,
    } for event in events]
    payments = env["mgs.event.payment"].search([
        ("company_id", "=", company.id), ("date", ">=", start), ("date", "<", end)])
    collected_pos = sum(payments.filtered(
        lambda payment: (payment.note or "").startswith("Cobrado en caja")).mapped("amount"))
    return {
        "rows": rows, "total": sum(events.mapped("amount_total")),
        "collected": sum(payments.mapped("amount")), "collected_pos": collected_pos,
        "available": True, "pending_return": sum(1 for event in events if event.pending_return),
    }


# ----------------------------------------------------------------------
# Correcciones
# ----------------------------------------------------------------------
def correcciones(env, company, start, end):
    # TODO Fase 5 (models/mgs_correction.py): sustituir por la consulta real
    # contra mgs.correction. Hasta entonces la sección se muestra vacía en
    # vez de romper el resto del informe.
    return []


# ----------------------------------------------------------------------
# Punto de entrada único
# ----------------------------------------------------------------------
def build(template):
    """Reúne, para una plantilla, solo los datos de las secciones marcadas.
    Es lo único que llaman la vista previa, el Excel y el PDF (Fases 3-4):
    así hay un solo sitio que decide qué datos van con qué filtro."""
    template.ensure_one()
    template._mgs_check_gestoria_integrity()
    env = template.env
    company = template.company_id
    start, end = madrid_day_range(env, template.date_from, template.date_to)
    category_ids = template.category_ids.ids
    product_ids = template.product_ids.ids
    payment_method_ids = template.payment_method_ids.ids

    data = {
        "template": template, "date_from": template.date_from, "date_to": template.date_to,
        "currency": company.currency_id, "generated_at": fields.Datetime.now(),
        "author": env.user.display_name, "is_gestoria": template.is_gestoria_master,
        "group_by": template.group_by, "order_by": template.order_by,
    }
    if template.section_resumen:
        data["resumen"] = resumen(env, company, start, end, category_ids, product_ids)
    if template.section_ventas:
        data["ventas"] = ventas(env, company, start, end, category_ids, product_ids,
                                 template.group_by, template.order_by)
    if template.section_devoluciones:
        data["devoluciones"] = devoluciones(env, company, start, end, category_ids,
                                            product_ids, template.order_by)
    if template.section_cobros:
        rows, available = cobros(env, company, start, end, payment_method_ids,
                                  category_ids, product_ids)
        data["cobros"] = rows
        data["cobros_available"] = available
    if template.section_mermas:
        data["mermas"] = mermas(env, company, start, end, category_ids, product_ids)
    if template.section_stock:
        rows, value, expired = stock(env, company, category_ids, product_ids)
        data["stock"] = rows
        data["stock_value"] = value
        data["stock_value_expired"] = expired
    if template.section_consumo:
        data["consumo"] = consumo(env, company, start, end, category_ids, product_ids)
    if template.section_eventos:
        data["eventos"] = eventos(env, company, template.date_from, template.date_to,
                                   start, end, category_ids, product_ids)
    if template.section_correcciones:
        data["correcciones"] = correcciones(env, company, start, end)
    return data
