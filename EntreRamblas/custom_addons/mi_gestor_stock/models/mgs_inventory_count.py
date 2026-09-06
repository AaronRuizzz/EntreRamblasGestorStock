import math
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare
from .mgs_permissions import require_manager


class InventoryCount(models.Model):
    _name = 'mgs.inventory.count'
    _description = 'Recuento físico'
    _order = 'id desc'

    name = fields.Char('Referencia', default='Nuevo', readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True, readonly=True)
    location_id = fields.Many2one('stock.location', required=True, string='Ubicación',
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]")
    state = fields.Selection([('draft', 'Preparación'), ('counting', 'Contando'), ('done', 'Aplicado'), ('cancelled', 'Cancelado')],
                            string='Estado', default='draft', readonly=True)
    note = fields.Text('Motivo / observaciones', required=True)
    prepared_at = fields.Datetime(readonly=True, string='Existencias consultadas')
    applied_at = fields.Datetime(readonly=True, string='Aplicado el')
    applied_by = fields.Many2one('res.users', readonly=True, string='Aplicado por')
    cancelled_by = fields.Many2one('res.users', readonly=True, string='Cancelado por')
    cancelled_at = fields.Datetime(readonly=True, string='Cancelado el')
    line_ids = fields.One2many('mgs.inventory.count.line', 'count_id', string='Partidas')
    move_ids = fields.One2many('stock.move', 'mgs_count_id', readonly=True, string='Ajustes')

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            if set(vals) - {'location_id', 'note', 'company_id'}:
                raise AccessError(_('El estado y las líneas del recuento los genera el servidor.'))
            vals['company_id'] = self.env.company.id
            vals['name'] = self.env['ir.sequence'].next_by_code('mgs.inventory.count')
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        if set(vals) == {'line_ids'}:
            for record in self.sorted('id'):
                record._lock()
                if record.state != 'counting':
                    raise AccessError(_('Solo se anotan cantidades en un recuento abierto.'))
                for command in vals['line_ids']:
                    if (len(command) != 3 or command[0] != 1 or command[1] not in record.line_ids.ids or
                            set(command[2]) - {'counted_qty', 'checked'}):
                        raise AccessError(_('Solo se pueden anotar cantidades y revisión de las partidas preparadas.'))
            return super().write(vals)
        if set(vals) - {'location_id', 'note'} or any(record.state != 'draft' for record in self):
            raise AccessError(_('Solo se puede editar la preparación de un recuento.'))
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        if any(record.state != 'draft' for record in self):
            raise UserError(_('Los recuentos iniciados se conservan para trazabilidad.'))
        return super().unlink()

    def _lock(self):
        require_manager(self.env)
        self.ensure_one()
        self.check_access('write')
        if self.company_id != self.env.company:
            raise UserError(_('Selecciona la compañía del recuento.'))
        self.env.cr.execute('SELECT id FROM mgs_inventory_count WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def action_prepare(self):
        self._lock()
        if self.state in ('done', 'cancelled'):
            raise UserError(_('Este recuento ya está cerrado.'))
        if self.location_id.usage != 'internal' or self.location_id.company_id != self.company_id:
            raise UserError(_('Elige una ubicación interna de la compañía.'))
        if not (self.note or '').strip():
            raise UserError(_('Indica el motivo del recuento.'))
        quants = self.env['stock.quant'].search([
            ('company_id', '=', self.company_id.id), ('location_id', 'child_of', self.location_id.id),
            ('location_id.usage', '=', 'internal'), ('owner_id', '=', False), ('package_id', '=', False),
        ])
        if not quants:
            raise UserError(_('No hay partidas registradas en esta ubicación. Registra primero la recepción.'))
        keys = [(q.product_id.id, q.location_id.id, q.lot_id.id) for q in quants]
        if len(set(keys)) != len(keys):
            raise UserError(_('Hay existencias pendientes de consolidar por Odoo. Vuelve a preparar el recuento tras el mantenimiento de stock.'))
        self.line_ids.sudo().unlink()
        self.env['mgs.inventory.count.line'].sudo().create([{
            'count_id': self.id, 'quant_id': q.id, 'product_id': q.product_id.id,
            'lot_id': q.lot_id.id, 'location_id': q.location_id.id, 'expected_qty': q.quantity,
            'reserved_qty': q.reserved_quantity, 'snapshot_write_date': q.write_date,
        } for q in quants])
        super().write({'state': 'counting', 'prepared_at': fields.Datetime.now()})
        return True

    def action_apply(self):
        self._lock()
        self.line_ids.invalidate_recordset()
        if self.state == 'done':
            return True
        if self.state != 'counting' or not self.line_ids or any(not line.checked for line in self.line_ids):
            raise UserError(_('Revisa y marca todas las líneas antes de aplicar el recuento.'))
        quants = self.line_ids.quant_id.exists()
        if len(quants) != len(self.line_ids):
            raise UserError(_('Las existencias han cambiado. Recarga las partidas y vuelve a contar.'))
        self.env.cr.execute('SELECT id FROM stock_quant WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(quants.ids)])
        quants.invalidate_recordset()
        for line in self.line_ids:
            quant = line.quant_id
            precision = line.product_id.uom_id.rounding
            if (quant.write_date != line.snapshot_write_date or
                    float_compare(quant.quantity, line.expected_qty, precision_rounding=precision) or
                    float_compare(quant.reserved_quantity, line.reserved_qty, precision_rounding=precision)):
                raise UserError(_('Ha cambiado el stock de %s durante el recuento. Recarga y vuelve a contar.', line.product_id.display_name))
            if not math.isfinite(line.counted_qty) or line.counted_qty < 0 or float_compare(line.counted_qty, quant.reserved_quantity, precision_rounding=precision) < 0:
                raise UserError(_('El recuento no puede ser negativo ni inferior a las unidades reservadas.'))
        changed = self.line_ids.filtered(lambda line: float_compare(line.counted_qty, line.expected_qty,
            precision_rounding=line.product_id.uom_id.rounding) != 0)
        for line in changed:
            line.quant_id.with_context(inventory_mode=True).write({'inventory_quantity': line.counted_qty})
        if changed:
            changed.quant_id.with_context(inventory_name=self.name + ': ' + self.note, _mgs_count_record=self)._apply_inventory()
        super().write({'state': 'done', 'applied_at': fields.Datetime.now(), 'applied_by': self.env.uid})
        return True

    def action_cancel(self):
        self._lock()
        if self.state == 'done':
            raise UserError(_('Un ajuste aplicado se corrige mediante un nuevo recuento.'))
        if self.state != 'cancelled':
            super().write({'state': 'cancelled', 'cancelled_at': fields.Datetime.now(), 'cancelled_by': self.env.uid})
        return True


class InventoryCountLine(models.Model):
    _name = 'mgs.inventory.count.line'
    _description = 'Partida contada'

    count_id = fields.Many2one('mgs.inventory.count', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='count_id.company_id', store=True)
    quant_id = fields.Many2one('stock.quant', ondelete='set null', readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unidad')
    lot_id = fields.Many2one('stock.lot', string='Partida', readonly=True)
    location_id = fields.Many2one('stock.location', string='Ubicación', readonly=True)
    expected_qty = fields.Float('Según programa', readonly=True)
    reserved_qty = fields.Float(readonly=True)
    snapshot_write_date = fields.Datetime(readonly=True)
    counted_qty = fields.Float('Cantidad contada')
    checked = fields.Boolean('Revisado')
    difference = fields.Float('Diferencia', compute='_compute_difference')

    @api.depends('counted_qty', 'expected_qty')
    def _compute_difference(self):
        for line in self:
            line.difference = line.counted_qty - line.expected_qty

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('Las líneas se generan al preparar el recuento.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            require_manager(self.env)
            for count in self.count_id.sorted('id'):
                count._lock()
            if set(vals) - {'counted_qty', 'checked'} or any(line.count_id.state != 'counting' for line in self):
                raise AccessError(_('No se puede modificar una línea fuera del recuento abierto.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_('Recarga el recuento para regenerar las líneas.'))
        return super().unlink()


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_inventory_move_values(self, *args, **kwargs):
        vals = super()._get_inventory_move_values(*args, **kwargs)
        record = self.env.context.get('_mgs_count_record')
        if isinstance(record, models.BaseModel) and record._name == 'mgs.inventory.count':
            vals['mgs_count_id'] = record.id
        return vals


class StockMove(models.Model):
    _inherit = 'stock.move'
    mgs_count_id = fields.Many2one('mgs.inventory.count', readonly=True, copy=False, string='Recuento')

    @api.model_create_multi
    def create(self, vals_list):
        count = self.env.context.get('_mgs_count_record')
        for vals in vals_list:
            if vals.get('mgs_count_id') and not (isinstance(count, models.BaseModel) and
                    count._name == 'mgs.inventory.count' and count.id == vals['mgs_count_id']):
                raise AccessError(_('El vínculo al recuento lo establece el servidor.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'mgs_count_id' in vals:
            raise AccessError(_('No se puede cambiar el origen de un ajuste de recuento.'))
        return super().write(vals)
