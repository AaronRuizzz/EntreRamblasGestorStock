from odoo import Command, fields
from odoo.tests import TransactionCase, tagged, new_test_user
from odoo.exceptions import UserError, AccessError


@tagged('post_install', '-at_install')
class TestOpeningStock(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['product.category'].create({'name': 'Apertura prueba'})
        cls.product = cls.env['product.product'].create({'name': 'Flor apertura', 'is_storable': True,
            'tracking': 'lot', 'mgs_auto_lots': True, 'use_expiration_date': True,
            'categ_id': cls.category.id})
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        # Cuelga del almacén: `qty_available` solo suma los quants bajo la
        # ubicación vista del almacén (product._get_domain_locations), así que una
        # ubicación suelta mediría cero aunque el ajuste fuese correcto.
        cls.location = cls.env['stock.location'].create({'name': 'Apertura prueba', 'usage': 'internal',
            'location_id': cls.warehouse.lot_stock_id.id, 'company_id': cls.env.company.id})

    @classmethod
    def summer(cls):
        """1 de julio del año que viene: horario de verano de Madrid (UTC+2)."""
        return fields.Date.today().replace(year=fields.Date.today().year + 1, month=7, day=1)

    @classmethod
    def winter(cls):
        """15 de enero del año que viene: horario de invierno de Madrid (UTC+1)."""
        return fields.Date.today().replace(year=fields.Date.today().year + 1, month=1, day=15)

    def opening(self, **overrides):
        values = {'location_id': self.location.id,
            'line_ids': [Command.create({'product_id': self.product.id, 'quantity': 5, 'unit_cost': 2,
                'expiry_date': self.summer(), 'checked': True}),
                Command.create({'product_id': self.product.id, 'quantity': 3, 'unit_cost': 4, 'checked': True})]}
        values.update(overrides)
        return self.env['mgs.opening.stock'].create(values)

    def test_opening_is_inventory_and_idempotent(self):
        opening = self.opening()
        opening.action_apply()
        self.assertEqual(self.product.qty_available, 8)
        self.assertEqual(len(opening.line_ids.lot_id), 2)
        self.assertEqual(set(opening.line_ids.move_id.mapped('state')), {'done'})
        self.assertEqual(set(opening.line_ids.move_id.location_id.mapped('usage')), {'inventory'})
        self.assertEqual(set(opening.line_ids.move_id.mapped('is_inventory')), {True})
        self.assertEqual(opening.move_ids, opening.line_ids.move_id)
        # Una sola línea de movimiento por partida: la construcción manual añadía
        # otra sin lote y dejaba el doble de existencias.
        self.assertEqual(len(opening.line_ids.move_id.move_line_ids), 2)
        self.assertEqual(sorted(opening.line_ids.move_id.mapped('quantity')), [3, 5])
        self.assertEqual(sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in opening.line_ids.move_id.move_line_ids), 22)
        # Caduca al final del día de Madrid, guardado en UTC (verano: -2 h).
        self.assertEqual(str(opening.line_ids[0].lot_id.expiration_date),
                         '%s 21:59:59' % self.summer())
        # Sin fecha en la línea la partida no caduca: product_expiry inventaría
        # una caducidad de hoy y la mercancía nacería vencida.
        self.assertFalse(opening.line_ids[1].lot_id.expiration_date)
        quants = self.env['stock.quant'].search([('product_id', '=', self.product.id),
                                                 ('location_id', '=', self.location.id)])
        self.assertEqual(sorted(quants.mapped('quantity')), [3, 5])
        self.assertEqual(len(quants.lot_id), 2)
        opening.action_apply()
        self.assertEqual(self.product.qty_available, 8)
        self.assertEqual(len(opening.line_ids.move_id), 2)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening().action_apply()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            opening.line_ids[0].quantity = 99
        with self.assertRaises(UserError), self.env.cr.savepoint():
            opening.unlink()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            opening.line_ids[0].move_id.write({'mgs_opening_id': False})

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
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env['mgs.opening.stock'].with_user(staff).create({'location_id': self.location.id})

    def test_opening_rejects_invalid_lines_and_locations(self):
        for quantity, cost in [(0, 2), (-1, 2), (5, -1)]:
            opening = self.opening(line_ids=[Command.create({'product_id': self.product.id,
                'quantity': quantity, 'unit_cost': cost, 'checked': True})])
            with self.assertRaises(UserError), self.env.cr.savepoint():
                opening.action_apply()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening(line_ids=[]).action_apply()
        # Ubicación interna pero fuera del almacén: guardaría existencias que el
        # resto del programa no vería.
        loose = self.env['stock.location'].create({'name': 'Fuera de almacén', 'usage': 'internal',
                                                   'company_id': self.env.company.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening(location_id=loose.id).action_apply()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening(location_id=self.warehouse.lot_stock_id.location_id.id).action_apply()
        # Producto sin partidas automáticas: el TPV no sabría qué lote descontar.
        manual = self.env['product.product'].create({'name': 'Flor sin partidas', 'is_storable': True})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening(line_ids=[Command.create({'product_id': manual.id, 'quantity': 2,
                'unit_cost': 1, 'checked': True})]).action_apply()
        self.assertEqual(self.product.qty_available, 0)

    def test_expiry_follows_madrid_winter_time(self):
        opening = self.opening(line_ids=[Command.create({'product_id': self.product.id, 'quantity': 2,
            'unit_cost': 1, 'expiry_date': self.winter(), 'checked': True})])
        opening.action_apply()
        # En invierno Madrid va una hora por delante de UTC, no dos.
        self.assertEqual(str(opening.line_ids.lot_id.expiration_date), '%s 22:59:59' % self.winter())
        self.assertEqual(fields.Datetime.context_timestamp(
            opening, opening.line_ids.lot_id.expiration_date).date(), self.winter())

    def test_opening_is_not_a_purchase_but_counts_as_stock_value(self):
        self.opening().action_apply()
        report = self.env['mgs.monthly.report'].create({
            'date_from': fields.Date.today(), 'date_to': fields.Date.today(),
            'category_id': self.category.id})
        data = report.mgs_get_report_data()
        self.assertEqual(data['purchases'], 0)
        self.assertEqual(data['purchased_qty'], 0)
        self.assertEqual(data['stock_value'], 22)

    def test_reception_closes_the_door_to_a_later_opening(self):
        self.env['mgs.reception'].create({'line_ids': [Command.create({
            'product_id': self.product.id, 'quantity': 4, 'unit_cost': 3})]}).action_confirm()
        self.assertEqual(self.product.qty_available, 4)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.opening().action_apply()
        self.assertEqual(self.product.qty_available, 4)
