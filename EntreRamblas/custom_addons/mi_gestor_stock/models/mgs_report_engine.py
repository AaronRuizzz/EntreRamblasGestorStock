# -*- coding: utf-8 -*-
"""Utilidades de consulta compartidas por los informes que sí quedan en el
programa (el informe mensual en PDF/CSV, `mgs_monthly_report.py`, y el
historial de correcciones).

Este módulo llevaba antes el motor completo de los «Informes personalizados»
(`mgs.report.template`): una plantilla reutilizable con secciones marcables,
filtros y vista previa, más la clasificación «Excluir de informes» (alias
«en B») de cada línea de venta. La propietaria ha decidido llevar esa parte
en papel, fuera del programa, así que se ha retirado por completo —modelos,
vistas, menús y la columna de la base de datos— en la versión 18.0.7.0.0 (ver
migrations/18.0.7.0.0/pre-migrate.py). Lo que queda aquí es solo lo que el
informe mensual seguía necesitando.
"""
from odoo import _

from .mgs_permissions import SOLD_STATES


def report_line_domain(company, start, end, category_ids=None, product_ids=None):
    """Dominio común de líneas de venta para el informe mensual."""
    return _category_domain(category_ids or []) + _product_domain(product_ids or []) + [
        ("company_id", "=", company.id),
        ("order_id.date_order", ">=", start), ("order_id.date_order", "<", end),
        ("order_id.state", "in", SOLD_STATES),
    ]


def payment_rows(env, company, start, end, payment_method_ids=None, category_ids=None,
                 product_ids=None):
    """Cobros prorrateados por el bruto incluido de cada ticket.

    Se calcula por ticket antes de agrupar por método: un ticket mixto mantiene
    la proporción en efectivo/tarjeta en lugar de inventar una asignación.
    """
    orders = env["pos.order"].search([
        ("company_id", "=", company.id), ("state", "in", SOLD_STATES),
        ("date_order", ">=", start), ("date_order", "<", end),
    ])
    included_by_order = {}
    for line in env["pos.order.line"].search(
            report_line_domain(company, start, end, category_ids, product_ids)):
        included_by_order.setdefault(line.order_id.id, env["pos.order.line"])
        included_by_order[line.order_id.id] |= line
    grouped = {}
    for order in orders:
        lines = included_by_order.get(order.id, env["pos.order.line"])
        all_lines = order.lines.filtered(lambda line: line.qty != 0)
        total = sum(abs(line.price_subtotal_incl) for line in all_lines)
        included = sum(abs(line.price_subtotal_incl) for line in lines)
        if total:
            ratio = included / total
        elif all_lines:
            ratio = len(lines) / len(all_lines)
        else:
            ratio = 0.0
        for payment in order.payment_ids:
            if payment.payment_date < start or payment.payment_date >= end:
                continue
            if payment_method_ids and payment.payment_method_id.id not in payment_method_ids:
                continue
            amount = company.currency_id.round(payment.amount * ratio)
            if not amount:
                continue
            method = payment.payment_method_id
            deferred = method.type == "pay_later"
            row = grouped.setdefault(method.id, {
                "name": method.name + (_(" (cuenta cliente, no cobrado)") if deferred else ""),
                "received": 0.0, "returned": 0.0, "deferred": deferred, "count": 0,
            })
            row["received" if amount >= 0 else "returned"] += abs(amount)
            row["count"] += 1
    return sorted(grouped.values(), key=lambda row: row["name"]), True


def _category_domain(category_ids, field="product_id.categ_id"):
    return [(field, "child_of", category_ids)] if category_ids else []


def _product_domain(product_ids, field="product_id"):
    return [(field, "in", product_ids)] if product_ids else []


def correcciones(env, company, start, end):
    """Filas del historial de correcciones (ver models/mgs_correction.py)."""
    return env["mgs.correction"]._mgs_report_rows(company, start, end)
