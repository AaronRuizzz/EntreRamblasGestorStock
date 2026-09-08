import base64

from odoo.tests import TransactionCase, tagged, new_test_user
from odoo.exceptions import UserError, AccessError

HEADER = 'codigo;nombre;categoria;unidad;precio_venta;coste;iva'


def sheet(*rows):
    return base64.b64encode(('\n'.join((HEADER,) + rows)).encode('utf-8-sig'))


@tagged('post_install', '-at_install')
class TestCatalogImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['product.category'].create({'name': 'Flor cortada'})

    def wizard(self, *rows, **values):
        data = {'file': sheet(*rows), 'filename': 'catalogo.csv'}
        data.update(values)
        return self.env['mgs.catalog.import'].create(data)

    def test_valid_sheet_creates_the_catalogue(self):
        wiz = self.wizard(
            '8412345678905;Rosa roja tallo largo;Flor cortada;Unidades;2,50;1,10;10',
            ';Jarrón de cristal;Flor cortada;Unidades;12.00;6.25;21',
            '# esta línea de ayuda se ignora;;;;;;',
        )
        wiz.action_check()
        self.assertEqual(wiz.error_count, 0, wiz.summary)
        self.assertEqual(wiz.state, 'checked')
        self.assertEqual(len(wiz.line_ids), 2)
        wiz.action_apply()
        self.assertEqual(wiz.state, 'done')
        rosa, jarron = wiz.line_ids.product_id
        self.assertEqual(rosa.barcode, '8412345678905')
        self.assertEqual(rosa.list_price, 2.5)
        self.assertEqual(rosa.standard_price, 1.1)
        self.assertEqual(rosa.categ_id, self.category)
        self.assertEqual(rosa.taxes_id.amount, 10)
        self.assertEqual(jarron.taxes_id.amount, 21)
        # Sin código en la hoja, el programa genera uno interno imprimible.
        self.assertTrue(jarron.barcode and jarron.barcode.isdigit() and len(jarron.barcode) == 13)
        for product in (rosa, jarron):
            self.assertTrue(product.is_storable and product.available_in_pos and product.sale_ok)
            self.assertEqual(product.tracking, 'lot')
            self.assertTrue(product.mgs_auto_lots and product.use_expiration_date)
        # Segunda pulsación: no duplica el catálogo.
        wiz.action_apply()
        self.assertEqual(len(wiz.line_ids.product_id), 2)

    def test_nothing_is_created_while_a_row_is_wrong(self):
        wiz = self.wizard(
            '8412345678905;Rosa buena;Flor cortada;Unidades;2,50;1,10;10',
            ';Rosa sin iva;Flor cortada;Unidades;2,50;1,10;7',
        )
        wiz.action_check()
        self.assertEqual(wiz.error_count, 1)
        self.assertEqual(wiz.state, 'draft')
        with self.assertRaises(UserError), self.env.cr.savepoint():
            wiz.action_apply()
        self.assertFalse(self.env['product.template'].search_count([('name', '=', 'Rosa buena')]))

    def test_duplicates_inside_the_sheet_and_against_the_catalogue(self):
        self.env['product.template'].create({'name': 'Clavel blanco', 'barcode': '8400000000017'})
        wiz = self.wizard(
            '8412345678905;Rosa uno;;Unidades;2,50;1,10;10',
            '8412345678905;Rosa dos;;Unidades;2,50;1,10;10',
            ';Rosa uno;;Unidades;2,50;1,10;10',
            ';Clavel blanco;;Unidades;2,50;1,10;10',
            '8400000000017;Clavel repetido por código;;Unidades;2,50;1,10;10',
        )
        wiz.action_check()
        self.assertEqual(wiz.error_count, 4)
        messages = ' | '.join(wiz.line_ids.mapped('message'))
        self.assertIn('código repetido', messages)
        self.assertIn('nombre repetido', messages)
        self.assertIn('ya existe un producto con ese nombre', messages)
        self.assertIn('ya hay un producto con ese código', messages)

    def test_zeros_and_negatives(self):
        rows = ('8412345678905;Rosa gratis;;Unidades;0;1,10;10',
                ';Rosa sin coste;;Unidades;2,50;0;10',
                ';Rosa negativa;;Unidades;-1;1,10;10',
                ';Rosa sin número;;Unidades;dos euros;1,10;10')
        wiz = self.wizard(*rows)
        wiz.action_check()
        self.assertEqual(wiz.error_count, 4)
        # Los ceros se aceptan solo si la dueña lo confirma; lo demás sigue mal.
        confirmed = self.wizard(*rows, allow_zero_prices=True)
        confirmed.action_check()
        self.assertEqual(confirmed.error_count, 2)

    def test_unknown_category_needs_an_explicit_yes(self):
        wiz = self.wizard('8412345678905;Rosa;Categoria con erata;Unidades;2,50;1,10;10')
        wiz.action_check()
        self.assertEqual(wiz.error_count, 1)
        self.assertIn('no existe', wiz.line_ids.message)
        allowed = self.wizard('8412345678905;Rosa;Categoría nueva de verdad;Unidades;2,50;1,10;10',
                              allow_new_categories=True)
        allowed.action_check()
        self.assertEqual(allowed.error_count, 0, allowed.summary)
        self.assertIn('Categoría nueva de verdad', allowed.summary)
        allowed.action_apply()
        self.assertEqual(allowed.line_ids.product_id.categ_id.name, 'Categoría nueva de verdad')

    def test_broken_headers_and_empty_sheets(self):
        for content in (b'', b'nombre;precio\nRosa;2', b'\n\n'):
            wiz = self.env['mgs.catalog.import'].create({'file': base64.b64encode(content)})
            with self.assertRaises(UserError), self.env.cr.savepoint():
                wiz.action_check()
        only_header = self.env['mgs.catalog.import'].create({'file': sheet()})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            only_header.action_check()

    def test_only_the_owner_imports_the_catalogue(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login='catalog_staff', groups='mi_gestor_stock.group_mgs_user',
            company_id=self.env.company.id)
        wiz = self.wizard('8412345678905;Rosa;Flor cortada;Unidades;2,50;1,10;10')
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            wiz.with_user(staff).action_check()
        wiz.action_check()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            wiz.with_user(staff).action_apply()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            wiz.line_ids.with_user(staff).write({'price': 99})

    def test_template_is_downloadable_and_round_trips(self):
        wiz = self.env['mgs.catalog.import'].create({})
        action = wiz.action_download_template()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        template = base64.b64decode(wiz.template_file).decode('utf-8-sig')
        header = template.splitlines()[0]
        # La plantilla que se descarga tiene que valer tal cual como cabecera.
        reused = self.env['mgs.catalog.import'].create({
            'file': base64.b64encode(('%s\n8412345678905;Rosa;;Unidades;2,50;1,10;10'
                                      % header).encode('utf-8-sig'))})
        reused.action_check()
        self.assertEqual(reused.error_count, 0, reused.summary)
