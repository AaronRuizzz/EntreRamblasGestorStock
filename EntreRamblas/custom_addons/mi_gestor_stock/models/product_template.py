# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # En una floristería física, todos los productos creados deben ser por defecto:
    # 1. Almacenables (con control de stock real en tienda)
    # 2. Disponibles para venta
    # 3. Disponibles en el TPV (Punto de Venta)
    is_storable = fields.Boolean(default=True)
    sale_ok = fields.Boolean(default=True)
    available_in_pos = fields.Boolean(default=True)
