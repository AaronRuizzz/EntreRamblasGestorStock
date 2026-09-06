import math
from datetime import datetime, time
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .mgs_permissions import require_manager


class OpeningStock(models.Model):
    _name = 'mgs.opening.stock'
    _description = 'Existencias iniciales'

    name = fields.Char('Referencia', default='Apertura de existencias', required=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, required=True, readonly=True)
    location_id = fields.Many2one('stock.location', 'Ubicación', required=True,
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    state = fields.Selection([('draft', 'Preparación'), ('done', 'Aplicado')], default='draft', readonly=True)
    line_ids = fields.One2many('mgs.opening.stock.line', 'opening_id', 'Partidas iniciales')
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

    def action_apply(self):
        require_manager(self.env)
        self.ensure_one()
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM mgs_opening_stock WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.state == 'done':
            return True
        if self.company_id != self.env.company or self.location_id.company_id != self.company_id or self.location_id.usage != 'internal':
            raise UserError(_('Elige una ubicación interna de la compañía activa.'))
        if not self.line_ids:
            raise UserError(_('Añade las partidas que existen al comenzar.'))
        products = self.line_ids.product_id
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
        for line in self.line_ids:
            product = line.product_id.with_company(self.company_id)
            source = product.property_stock_inventory
            if not source or source.usage != 'inventory':
                raise UserError(_('Falta la ubicación de ajuste de inventario del producto.'))
            lot_vals = {'name': 'INI-%s-%s' % (self.id, line.id), 'product_id': product.id,
                'company_id': self.company_id.id, 'mgs_unit_cost': line.unit_cost,
                'mgs_cost_recorded': True, 'mgs_received_at': fields.Datetime.now()}
            if line.expiry_date:
                lot_vals['expiration_date'] = pytz.timezone('Europe/Madrid').localize(
                    datetime.combine(line.expiry_date, time(23, 59, 59))).astimezone(pytz.UTC).replace(tzinfo=None)
            lot = self.env['stock.lot'].create(lot_vals)
            move = self.env['stock.move'].create({'name': self.name, 'origin': 'Apertura %s' % self.id,
                'product_id': product.id, 'product_uom': product.uom_id.id, 'product_uom_qty': line.quantity,
                'location_id': source.id, 'location_dest_id': self.location_id.id, 'company_id': self.company_id.id,
                'is_inventory': True})
            move._action_confirm(merge=False)
            self.env['stock.move.line'].create({'move_id': move.id, 'product_id': product.id,
                'product_uom_id': product.uom_id.id, 'quantity': line.quantity, 'lot_id': lot.id,
                'location_id': source.id, 'location_dest_id': self.location_id.id})
            move.picked = True
            move._action_done()
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
