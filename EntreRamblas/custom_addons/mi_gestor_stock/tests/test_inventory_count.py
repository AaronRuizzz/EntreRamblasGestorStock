from odoo.tests import TransactionCase, tagged, new_test_user
from odoo.exceptions import AccessError, UserError


@tagged('post_install', '-at_install')
class TestInventoryCount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.location = cls.env['stock.location'].create({'name': 'Ubicación de prueba recuento',
            'usage': 'internal', 'company_id': cls.env.company.id})
        cls.product = cls.env['product.product'].create({'name': 'Rosa de recuento',
            'tracking': 'lot', 'is_storable': True, 'standard_price': 99})
        cls.lot = cls.env['stock.lot'].create({'name': 'Partida recuento', 'product_id': cls.product.id,
            'company_id': cls.env.company.id, 'mgs_unit_cost': 2, 'mgs_cost_recorded': True})
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.location, 5, lot_id=cls.lot)

    def prepare(self):
        count = self.env['mgs.inventory.count'].create({'location_id': self.location.id, 'note': 'Revisión semanal'})
        count.action_prepare()
        self.assertEqual(len(count.line_ids), 1)
        return count

    def test_count_creates_historical_adjustment_once(self):
        count = self.prepare()
        count.write({'line_ids': [(1, count.line_ids.id, {'counted_qty': 3, 'checked': True})]})
        count.action_apply()
        self.assertEqual(count.state, 'done')
        self.assertEqual(count.line_ids.quant_id.quantity, 3)
        self.assertEqual(len(count.move_ids), 1)

        unchanged = self.prepare()
        unchanged.line_ids.write({'counted_qty': 3, 'checked': True})
        unchanged.action_apply()
        self.assertEqual(unchanged.state, 'done')
        self.assertFalse(unchanged.move_ids)
        self.assertEqual(count.move_ids.state, 'done')
        self.assertEqual(count.move_ids.move_line_ids.mgs_unit_cost, 2)
        count.action_apply()
        self.assertEqual(count.line_ids.quant_id.quantity, 3)
        self.assertEqual(len(count.move_ids), 1)

    def test_changed_stock_requires_recount(self):
        count = self.prepare()
        with self.assertRaises(UserError):
            count.action_apply()
        count.line_ids.write({'counted_qty': 3, 'checked': True})
        self.env['stock.quant']._update_available_quantity(self.product, self.location, -1, lot_id=self.lot)
        with self.assertRaises(UserError):
            count.action_apply()
        self.assertEqual(count.line_ids.quant_id.quantity, 4)
        self.assertFalse(count.move_ids)
        count.action_prepare()
        self.assertEqual(count.line_ids.expected_qty, 4)
        self.assertFalse(count.line_ids.checked)

    def test_count_permissions_and_reservations(self):
        count = self.prepare()
        owner = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login='mgs_count_owner', groups='mi_gestor_stock.group_mgs_manager')
        with self.assertRaises(AccessError):
            count.line_ids.with_user(owner).write({'expected_qty': 100})
        with self.assertRaises(AccessError):
            count.with_user(owner).write({'state': 'done'})
        count.line_ids.quant_id.write({'reserved_quantity': 2})
        count.action_prepare()
        count.line_ids.write({'counted_qty': 1, 'checked': True})
        with self.assertRaises(UserError):
            count.action_apply()
        self.assertEqual(count.line_ids.quant_id.quantity, 5)
        count.action_cancel()
        self.assertEqual(count.state, 'cancelled')
        self.assertFalse(count.move_ids)
        with self.assertRaises(UserError):
            count.action_prepare()
