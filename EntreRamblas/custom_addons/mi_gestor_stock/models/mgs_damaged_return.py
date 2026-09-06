from odoo import api, fields, models, _
from odoo.exceptions import UserError, AccessError


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    mgs_damaged_return = fields.Boolean('Devolución no recuperable', copy=False)

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + ['mgs_damaged_return']

    def write(self, vals):
        if 'mgs_damaged_return' in vals:
            for line in self:
                if line.mgs_move_ids and bool(vals['mgs_damaged_return']) != line.mgs_damaged_return:
                    raise UserError(_('El estado de la mercancía no se cambia después de mover el stock.'))
        return super().write(vals)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _create_order_picking(self):
        damaged = self.lines.filtered('mgs_damaged_return')
        if any(line.qty >= 0 or not line.refunded_orderline_id or not line.product_id.is_storable
               or not (line.product_id.mgs_auto_lots or line.product_id.tracking == 'none') for line in damaged):
            raise UserError(_('Marca como deterioradas solo devoluciones vinculadas de productos de stock compatibles.'))
        result = super()._create_order_picking()
        # El retorno y la merma forman parte de la misma transacción de venta.
        for line in damaged:
            for returned in line.sudo().mgs_move_ids.move_line_ids.sorted('id'):
                self.env.cr.execute('SELECT id FROM stock_move_line WHERE id = %s FOR UPDATE', [returned.id])
                if self.env['stock.scrap'].sudo().search_count([('mgs_return_line_id', '=', returned.id)]):
                    continue
                scrap = self.env['stock.scrap'].sudo().with_context(_mgs_return_line=returned).create({
                    'product_id': returned.product_id.id, 'product_uom_id': returned.product_id.uom_id.id,
                    'scrap_qty': returned.quantity_product_uom, 'lot_id': returned.lot_id.id,
                    'location_id': returned.location_dest_id.id, 'company_id': returned.company_id.id,
                    'origin': line.order_id.pos_reference or line.order_id.name,
                    'mgs_reason': 'return', 'mgs_return_line_id': returned.id,
                })
                scrap.do_scrap()
        return result


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    mgs_return_line_id = fields.Many2one('stock.move.line', 'Movimiento devuelto', readonly=True, copy=False)
    _sql_constraints = [('mgs_return_line_unique', 'unique(mgs_return_line_id)', 'La devolución ya tiene una merma vinculada.')]

    @api.model_create_multi
    def create(self, vals_list):
        source = self.env.context.get('_mgs_return_line')
        for vals in vals_list:
            if vals.get('mgs_return_line_id') and not (isinstance(source, models.BaseModel)
                    and source._name == 'stock.move.line' and source.id == vals['mgs_return_line_id']):
                raise AccessError(_('El servidor vincula la merma a la devolución.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'mgs_return_line_id' in vals:
            raise AccessError(_('No se puede cambiar el origen de la merma.'))
        return super().write(vals)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _action_done(self):
        source = self.env.context.get('_mgs_return_line')
        if isinstance(source, models.BaseModel) and source._name == 'stock.move.line':
            for line in self.sudo().filtered(lambda item: not item.mgs_cost_recorded):
                line.write({'mgs_unit_cost': source.mgs_unit_cost, 'mgs_cost_recorded': True})
        return super()._action_done()
