# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    # Odoo no trae categorías archivables. La floristería no quiere ver las
    # categorías de fábrica («Todo», «Todo/Vendible», «Todo/Gastos»,
    # «Todo/TPV»): son ruido para la dependienta y no significan nada en la
    # tienda. Con `active` se archivan en data/ux_defaults.xml y desaparecen
    # de todos los desplegables; la dueña crea las suyas sobre la marcha
    # (recepción → «Producto nuevo» → escribir la categoría y «Crear»).
    active = fields.Boolean(default=True)
