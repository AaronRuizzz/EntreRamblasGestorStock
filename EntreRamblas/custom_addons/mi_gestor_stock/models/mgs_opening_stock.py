import math
from datetime import datetime, time
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .mgs_permissions import require_manager

MADRID = pytz.timezone('Europe/Madrid')


class OpeningStock(models.Model):
    _name = 'mgs.opening.stock'
    _description = 'Existencias iniciales'

    name = fields.Char('Referencia', default='Apertura de existencias', required=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, required=True, readonly=True)
    location_id = fields.Many2one('stock.location', 'Ubicación', required=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    state = fields.Selection([('draft', 'Preparación'), ('done', 'Aplicado')], default='draft', readonly=True)
    line_ids = fields.One2many('mgs.opening.stock.line', 'opening_id', 'Partidas iniciales')
    move_ids = fields.One2many('stock.move', 'mgs_opening_id', 'Ajustes', readonly=True)
    applied_by = fields.Many2one('res.users', 'Aplicado por', readonly=True)
    applied_at = fields.Datetime('Aplicado el', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            if set(vals) - {'name', 'location_id', 'line_ids'}:
                raise AccessError(_('Los datos de aplicación los establece el servidor.'))
        return super().create(vals_list)

    def _lock_draft(self):
        require_manager(self.env)
        self.check_access('write')
        for record in self.sorted('id'):
            self.env.cr.execute('SELECT id FROM mgs_opening_stock WHERE id=%s FOR UPDATE', [record.id])
            record.invalidate_recordset()
            if record.state != 'draft':
                raise UserError(_('La apertura aplicada se conserva sin modificaciones.'))

    def write(self, vals):
        self._lock_draft()
        if set(vals) - {'name', 'location_id', 'line_ids'}:
            raise AccessError(_('Los datos de aplicación los establece el servidor.'))
        return super().write(vals)

    def unlink(self):
        self._lock_draft()
        return super().unlink()

    def _check_location(self):
        """La ubicación tiene que colgar de un almacén de la compañía.

        `qty_available` (avisos, panel, TPV) solo suma los quants que cuelgan de
        la ubicación vista de un almacén: ver `product._get_domain_locations`. Una
        ubicación interna suelta guardaría existencias que el informe de stock ve
        y el resto del programa no. Es preferible rechazarla que dejar dos cifras
        distintas de la misma mercancía."""
        if (self.company_id != self.env.company or self.location_id.company_id != self.company_id
                or self.location_id.usage != 'internal'):
            raise UserError(_('Elige una ubicación interna de la compañía activa.'))
        views = self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)]).view_location_id
        path = self.location_id.parent_path or ''
        if not any(path.startswith(view.parent_path) for view in views if view.parent_path):
            raise UserError(_('Elige una ubicación del almacén de la tienda: fuera de él las existencias '
                              'no contarían como stock disponible.'))

    def _lot_values(self, line, product):
        expiry = False
        if line.expiry_date:
            expiry = MADRID.localize(datetime.combine(line.expiry_date, time.max)).astimezone(
                pytz.UTC).replace(tzinfo=None, microsecond=0)
        return {
            'name': 'INI-%s-%s' % (self.id, line.id),
            'product_id': product.id,
            'company_id': self.company_id.id,
            # Explícito aunque sea falso: product_expiry calcula una caducidad a
            # partir de hoy cuando el campo no viene en el create, y una partida
            # de apertura sin fecha nacería caducada.
            'expiration_date': expiry,
            'mgs_unit_cost': line.unit_cost,
            'mgs_cost_recorded': True,
            'mgs_received_at': fields.Datetime.now(),
        }

    def action_apply(self):
        require_manager(self.env)
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM mgs_opening_stock WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.state == 'done':
            return True
        self._check_location()
        if not self.line_ids:
            raise UserError(_('Añade las partidas que existen al comenzar.'))
        products = self.line_ids.product_id
        # Mismo candado que toma la recepción (mgs_reception.action_confirm): sin
        # él, una entrada de mercancía simultánea podría colarse entre esta
        # comprobación y el ajuste, y la apertura duplicaría las existencias.
        self.env.cr.execute('SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(products.ids)])
        if self.env['stock.move'].search_count([('product_id', 'in', products.ids), ('company_id', '=', self.company_id.id), ('state', '=', 'done')]) or self.env['stock.quant'].search_count([
                ('product_id', 'in', products.ids), ('company_id', '=', self.company_id.id), ('quantity', '!=', 0)]):
            raise UserError(_('Algún producto ya tiene existencias o movimientos. Usa recepción para compras y recuento para correcciones.'))
        for line in self.line_ids:
            if not line.product_id.is_storable or line.product_id.tracking != 'lot' or not line.product_id.mgs_auto_lots:
                raise UserError(_('La apertura requiere productos almacenables con partidas automáticas. Configura primero el catálogo.'))
            if (not math.isfinite(line.quantity) or line.quantity <= 0 or not math.isfinite(line.unit_cost) or line.unit_cost < 0):
                raise UserError(_('Indica cantidades positivas y costes finitos no negativos.'))
            if not line.checked:
                raise UserError(_('Revisa y marca cada partida antes de aplicar.'))
            if not line.product_id.with_company(self.company_id).property_stock_inventory.filtered(
                    lambda location: location.usage == 'inventory'):
                raise UserError(_('Falta la ubicación de ajuste de inventario del producto.'))
        for line in self.line_ids:
            product = line.product_id.with_company(self.company_id)
            lot = self.env['stock.lot'].create(self._lot_values(line, product))
            # Ajuste de inventario nativo: Odoo crea el movimiento is_inventory con
            # su única línea y la partida ya puesta. Construirlo a mano dejaba dos
            # líneas (la automática sin partida y la nuestra) y duplicaba el stock.
            quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product.id, 'location_id': self.location_id.id,
                'lot_id': lot.id, 'inventory_quantity': line.quantity,
            })
            quant.with_context(inventory_name=_('Existencias iniciales: %s', self.name),
                               _mgs_opening_record=self)._apply_inventory()
            move = self.env['stock.move.line'].search([('lot_id', '=', lot.id)]).move_id
            move.ensure_one()
            super(OpeningStockLine, line).write({'lot_id': lot.id, 'move_id': move.id})
        super().write({'state': 'done', 'applied_by': self.env.uid, 'applied_at': fields.Datetime.now()})
        return True


class OpeningStockLine(models.Model):
    _name = 'mgs.opening.stock.line'
    _description = 'Partida de apertura'

    opening_id = fields.Many2one('mgs.opening.stock', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='opening_id.company_id', store=True)
    product_id = fields.Many2one('product.product', 'Producto', required=True)
    quantity = fields.Float('Cantidad', required=True)
    unit_cost = fields.Float('Coste unitario', required=True, digits='Product Price')
    expiry_date = fields.Date('Caduca el')
    checked = fields.Boolean('Revisado')
    lot_id = fields.Many2one('stock.lot', 'Partida generada', readonly=True, copy=False)
    move_id = fields.Many2one('stock.move', 'Ajuste', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals) - {'opening_id', 'product_id', 'quantity', 'unit_cost', 'expiry_date', 'checked'}:
                raise AccessError(_('El servidor genera las partidas y ajustes.'))
            self.env['mgs.opening.stock'].browse(vals.get('opening_id'))._lock_draft()
        return super().create(vals_list)

    def write(self, vals):
        self.opening_id._lock_draft()
        if set(vals) - {'product_id', 'quantity', 'unit_cost', 'expiry_date', 'checked'}:
            raise AccessError(_('No se puede cambiar el origen de la partida.'))
        return super().write(vals)

    def unlink(self):
        self.opening_id._lock_draft()
        return super().unlink()


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_inventory_move_values(self, *args, **kwargs):
        vals = super()._get_inventory_move_values(*args, **kwargs)
        record = self.env.context.get('_mgs_opening_record')
        if isinstance(record, models.BaseModel) and record._name == 'mgs.opening.stock':
            vals['mgs_opening_id'] = record.id
        return vals


class StockMove(models.Model):
    _inherit = 'stock.move'
    mgs_opening_id = fields.Many2one('mgs.opening.stock', readonly=True, copy=False, string='Apertura')

    @api.model_create_multi
    def create(self, vals_list):
        opening = self.env.context.get('_mgs_opening_record')
        for vals in vals_list:
            if vals.get('mgs_opening_id') and not (isinstance(opening, models.BaseModel) and
                    opening._name == 'mgs.opening.stock' and opening.id == vals['mgs_opening_id']):
                raise AccessError(_('El vínculo con la apertura lo establece el servidor.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'mgs_opening_id' in vals:
            raise AccessError(_('No se puede cambiar el origen de un ajuste de apertura.'))
        return super().write(vals)
