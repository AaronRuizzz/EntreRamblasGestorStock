# -*- coding: utf-8 -*-
"""18.0.5.0.0 — Correcciones de ventas: venta con falta de stock, borrado de
línea, devoluciones guiadas, «Ventas y devoluciones», categorías que se
guardan solas y «Entradas y salidas».

Sobre una base ya instalada no hace falta tocar nada a mano:

  * Los campos nuevos (`mgs.stock.deficit`, `stock.lot.mgs_pending_review`,
    `stock.move.line.mgs_cost_estimated`, los tres campos de enlace al
    ticket en `mgs.stock.alert.notice`) describen hechos FUTUROS —una venta
    con falta de stock que todavía no ha pasado—, no una reinterpretación de
    datos ya guardados: nacen vacíos/False y no necesitan relleno.
  * `product.category.mgs_name_normalized` es un campo calculado y
    almacenado (`store=True`) sobre `name`: Odoo lo recalcula solo para las
    categorías ya existentes al crear la columna en este `-u`, sin que haga
    falta ningún script. No lleva restricción única a nivel de base de datos
    a propósito (`mgs_find_or_create` deduplica con un bloqueo consultivo en
    tiempo de escritura, no con un `_sql_constraints`): un UNIQUE aquí
    rompería con datos legítimos que ya tuviera la instalación o el resto de
    Odoo (dos categorías con el mismo nombre bajo padres distintos, datos de
    prueba de otros módulos...).
  * El archivado de «Ramo a medida» en `data/mgs_bouquet_data.xml` usa
    `noupdate="1"`: ese cambio solo se aplica en instalaciones NUEVAS. Una
    base ya instalada conserva el estado (activo o archivado) que ya tuviera
    esa ficha, tal y como exige que las actualizaciones no sean destructivas.

Este script no tiene, por tanto, ninguna operación que ejecutar; se deja
como marcador de versión y como sitio donde añadir algo si una futura
revisión de esta misma entrega lo necesitara."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _logger.info("mi_gestor_stock: actualizado a 18.0.5.0.0 (correcciones de ventas). "
                 "Nada que migrar: ver el docstring de este fichero.")
