from odoo import api, fields, models
from .mgs_permissions import COST_GROUPS, is_manager, require_manager


class ProductTemplate(models.Model):
    _inherit = "product.template"
    standard_price = fields.Float(groups=COST_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        return super().unlink()


class ProductProduct(models.Model):
    _inherit = "product.product"
    standard_price = fields.Float(groups=COST_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        return super().unlink()


class StockMove(models.Model):
    _inherit = "stock.move"
    price_unit = fields.Float(groups=COST_GROUPS)

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        return super().unlink()


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        return super().unlink()


class StockLot(models.Model):
    _inherit = "stock.lot"

    def write(self, vals):
        require_manager(self.env)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        return super().create(vals_list)


class PosOrder(models.Model):
    _inherit = "pos.order"
    margin = fields.Monetary(groups=COST_GROUPS)
    margin_percent = fields.Float(groups=COST_GROUPS)


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"
    total_cost = fields.Float(groups=COST_GROUPS)
    margin = fields.Monetary(groups=COST_GROUPS)
    margin_percent = fields.Float(groups=COST_GROUPS)

    @api.model
    def _load_pos_data_fields(self, config_id):
        values = super()._load_pos_data_fields(config_id)
        if not is_manager(self.env):
            values = [name for name in values if name not in {"total_cost", "margin", "margin_percent"}]
        return values


class PosOrderReport(models.Model):
    _inherit = "report.pos.order"
    margin = fields.Float(groups=COST_GROUPS)


class StockQuant(models.Model):
    _inherit = "stock.quant"

    def _apply_inventory(self):
        require_manager(self.env)
        return super()._apply_inventory()

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        require_manager(self.env)
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        return super().unlink()


class ProductSupplierInfo(models.Model):
    _inherit = "product.supplierinfo"
    price = fields.Float(groups=COST_GROUPS)
