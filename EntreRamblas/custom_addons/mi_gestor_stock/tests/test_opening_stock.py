from odoo import Command, fields
from odoo.tests import TransactionCase, tagged, new_test_user
from odoo.exceptions import UserError, AccessError


@tagged('post_install', '-at_install')
class TestOpeningStock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env['product.product'].create({'name': 'Flor apertura', 'is_storable': True,
            'tracking': 'lot', 'mgs_auto_lots': True, 'use_expiration_date': True})
        cls.location = cls.env['stock.location'].create({'name': 'Apertura prueba', 'usage': 'internal', 'company_id': cls.env.company.id})

    def opening(self):
        return self.env['mgs.opening.stock'].create({'location_id': self.location.id,
            'line_ids': [Command.create({'product_id': self.product.id, 'quantity': 5, 'unit_cost': 2,
                'expiry_date': '2080-06-01', 'checked': True}),
                Command.create({'product_id': self.product.id, 'quantity': 3, 'unit_cost': 4, 'checked': True})]})

    def test_opening_is_inventory_and_idempotent(self):
        opening = self.opening()
        opening.action_apply()
        self.assertEqual(self.product.qty_available, 8)
        self.assertEqual(len(opening.line_ids.lot_id), 2)
        self.assertEqual(set(opening.line_ids.move_id.mapped('state')), {'done'})
        self.assertEqual(set(opening.line_ids.move_id.location_id.mapped('usage')), {'inventory'})
        self.assertEqual(sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in opening.line_ids.move_id.move_line_ids), 22)
        self.assertEqual(str(opening.line_ids[0].lot_id.expiration_date), '2080-06-01 21:59:59')
        opening.action_apply()
        self.assertEqual(self.product.qty_available, 8)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening().action_apply()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            opening.line_ids[0].quantity = 99
        with self.assertRaises(UserError), self.env.cr.savepoint():
            opening.unlink()

    def test_opening_requires_review_and_manager(self):
        opening = self.opening()
        opening.line_ids[0].checked = False
        with self.assertRaises(UserError), self.env.cr.savepoint():
            opening.action_apply()
        self.assertEqual(self.product.qty_available, 0)
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)), login='opening_staff',
            groups='mi_gestor_stock.group_mgs_user', company_id=self.env.company.id)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            opening.with_user(staff).action_apply()
