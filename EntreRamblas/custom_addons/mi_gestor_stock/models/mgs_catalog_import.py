# -*- coding: utf-8 -*-
"""Alta del catálogo inicial desde una hoja de cálculo.

La tienda arranca con cientos de referencias y darlas de alta a mano en la
pantalla de recepción es inviable. Aquí se sube un CSV, se comprueba ENTERO
antes de tocar nada y solo entonces se crean los productos: si una sola fila
está mal, no se importa ninguna. Así la dueña corrige la hoja y vuelve a
subirla, en vez de quedarse con medio catálogo dentro.

Este asistente NO carga existencias: crea las fichas. El stock de apertura se
registra después en Stock → Existencias iniciales, que es quien deja el ajuste
de inventario con su partida, su coste y su caducidad.
"""
import base64
import csv
import io
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from .mgs_permissions import require_manager

# Columnas de la plantilla, en orden. La cabecera se compara normalizada, así
# que da igual el acento o la mayúscula que ponga Excel al guardar.
COLUMNS = ['codigo', 'nombre', 'categoria', 'unidad', 'precio_venta', 'coste', 'iva']
REQUIRED = ['nombre', 'precio_venta', 'coste', 'iva']
# IVA español al por menor. La dueña escribe el número; el asistente busca el
# impuesto de venta de la compañía con ese porcentaje. No se elige por defecto:
# el tipo aplicable a cada artículo lo decide ella, no el programa.
ALLOWED_VAT = ['0', '4', '10', '21']
EXAMPLE = ['8412345678905', 'Rosa roja tallo largo', 'Flor cortada', 'Unidades', '2,50', '1,10', '10']
# Las unidades de Odoo se llaman en inglés mientras no se cargue su traducción,
# y la dueña escribe la hoja en español. Estos son los nombres que de verdad va a
# teclear una floristería; cualquier otro se señala como error, no se adivina.
UNIT_ALIASES = {
    'unidad': 'uom.product_uom_unit', 'unidades': 'uom.product_uom_unit',
    'ud': 'uom.product_uom_unit', 'uds': 'uom.product_uom_unit',
    'tallo': 'uom.product_uom_unit', 'tallos': 'uom.product_uom_unit',
    'docena': 'uom.product_uom_dozen', 'docenas': 'uom.product_uom_dozen',
    'kg': 'uom.product_uom_kgm', 'kilo': 'uom.product_uom_kgm', 'kilos': 'uom.product_uom_kgm',
    'kilogramo': 'uom.product_uom_kgm', 'kilogramos': 'uom.product_uom_kgm',
    'g': 'uom.product_uom_gram', 'gramo': 'uom.product_uom_gram', 'gramos': 'uom.product_uom_gram',
    'l': 'uom.product_uom_litre', 'litro': 'uom.product_uom_litre', 'litros': 'uom.product_uom_litre',
    'm': 'uom.product_uom_meter', 'metro': 'uom.product_uom_meter', 'metros': 'uom.product_uom_meter',
    'cm': 'uom.product_uom_cm', 'centimetro': 'uom.product_uom_cm', 'centimetros': 'uom.product_uom_cm',
}


def normalize(text):
    table = str.maketrans('áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')
    return (text or '').strip().translate(table).lower().replace(' ', '_')


def find_by_name(model, name):
    """Busca por nombre tolerando idioma, mayúsculas y acentos.

    Las unidades y categorías vienen traducidas: `Unidades` en la pantalla puede
    ser `Units` en la base. Primero se pregunta al ORM, que resuelve la
    traducción activa, y si no encuentra nada se compara sin acentos: la dueña
    escribe la hoja a mano y «jarron» tiene que valer por «jarrón»."""
    if not (name or '').strip():
        return model.browse()
    found = model.search([('name', '=ilike', name.strip())], limit=1)
    if found:
        return found
    key = normalize(name)
    return model.search([]).filtered(lambda record: normalize(record.name) == key)[:1]


def parse_number(raw):
    """Acepta 1.234,56 y 1234.56: Excel en español escribe la primera."""
    text = (raw or '').strip().replace(' ', '')
    if not text:
        return None
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


class CatalogImport(models.TransientModel):
    _name = 'mgs.catalog.import'
    _description = 'Alta de catálogo inicial'
    _transient_max_hours = 8.0

    file = fields.Binary('Hoja de catálogo (CSV)', attachment=False)
    filename = fields.Char('Nombre del archivo')
    template_file = fields.Binary(readonly=True, attachment=False)
    template_filename = fields.Char(readonly=True)
    state = fields.Selection([('draft', 'Sin comprobar'), ('checked', 'Comprobado'),
                              ('done', 'Importado')], string='Estado', default='draft', readonly=True)
    line_ids = fields.One2many('mgs.catalog.import.line', 'import_id', readonly=True)
    error_count = fields.Integer('Filas con problemas', readonly=True)
    summary = fields.Text('Resultado de la comprobación', readonly=True)
    allow_zero_prices = fields.Boolean('Acepto precios o costes a cero',
        help='Un cero suele ser una casilla que se quedó vacía. Marca esta casilla '
             'solo si de verdad hay artículos sin precio o sin coste.')
    allow_new_categories = fields.Boolean('Crear las categorías que no existan',
        help='Sin marcar, una categoría mal escrita se señala como error en vez de '
             'crear una categoría nueva por una errata.')

    # ------------------------------------------------------------------
    # Plantilla
    # ------------------------------------------------------------------
    def action_download_template(self):
        require_manager(self.env)
        self.ensure_one()
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer, delimiter=';')
        writer.writerow(COLUMNS)
        writer.writerow(['# ejemplo: borra esta línea antes de subir la hoja'] + EXAMPLE[1:])
        writer.writerow(['# codigo vacío = el programa genera uno interno y podrás '
                         'imprimir la etiqueta'] + [''] * (len(COLUMNS) - 1))
        writer.writerow(['# iva: solo %s' % ', '.join(ALLOWED_VAT)] + [''] * (len(COLUMNS) - 1))
        content = buffer.getvalue().encode('utf-8-sig')
        self.write({'template_file': base64.b64encode(content),
                    'template_filename': 'plantilla-catalogo.csv'})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/web/content/mgs.catalog.import/%s/template_file/%s?download=true'
                       % (self.id, self.template_filename)}

    # ------------------------------------------------------------------
    # Comprobación
    # ------------------------------------------------------------------
    def _read_rows(self):
        try:
            raw = base64.b64decode(self.file or b'')
        except Exception:
            raise UserError(_('No se ha podido leer el archivo. Vuelve a subirlo.'))
        for encoding in ('utf-8-sig', 'utf-8', 'cp1252'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise UserError(_('El archivo no está en un texto legible. Guárdalo como CSV UTF-8.'))
        sample = text[:4096]
        delimiter = ';' if sample.count(';') >= sample.count(',') else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [row for row in reader if any((cell or '').strip() for cell in row)]
        if not rows:
            raise UserError(_('La hoja está vacía.'))
        header = [normalize(cell) for cell in rows[0]]
        missing = [column for column in REQUIRED if column not in header]
        if missing:
            raise UserError(_('Faltan columnas obligatorias en la cabecera: %s. '
                              'Descarga la plantilla y parte de ella.', ', '.join(missing)))
        index = {column: header.index(column) for column in COLUMNS if column in header}
        result = []
        for number, row in enumerate(rows[1:], start=2):
            if (row[0] or '').strip().startswith('#'):
                continue  # Líneas de ayuda de la plantilla.
            result.append((number, {column: (row[position].strip() if position < len(row) else '')
                                    for column, position in index.items()}))
        if not result:
            raise UserError(_('La hoja no trae ninguna fila de producto.'))
        return result

    def _find_uom(self, unit_name):
        """Primero el nombre tal cual (por si la unidad está traducida o es
        propia de la tienda) y después la lista de nombres en español."""
        found = find_by_name(self.env['uom.uom'], unit_name)
        if found:
            return found
        reference = UNIT_ALIASES.get(normalize(unit_name).replace('_', ''))
        return self.env.ref(reference, raise_if_not_found=False) if reference else self.env['uom.uom']

    def _tax_by_percent(self):
        taxes = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'), ('company_id', '=', self.env.company.id),
            ('amount_type', '=', 'percent'), ('amount', '>=', 0),
        ])
        found = {}
        for percent in ALLOWED_VAT:
            # "21% G" es el IVA general de bienes de l10n_es; se prefiere al
            # de servicios ("S") porque la floristería vende mercancía.
            match = taxes.filtered(lambda tax: abs(tax.amount - float(percent)) < 0.001)
            goods = match.filtered(lambda tax: (tax.name or '').strip().endswith(' G'))
            found[percent] = (goods or match)[:1]
        return found

    def action_check(self):
        require_manager(self.env)
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_('Este catálogo ya se ha importado. Abre uno nuevo para otra hoja.'))
        if not self.file:
            raise UserError(_('Sube la hoja de catálogo antes de comprobarla.'))
        rows = self._read_rows()
        taxes = self._tax_by_percent()
        Product = self.env['product.template']
        Category = self.env['product.category']
        Uom = self.env['uom.uom']
        default_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)

        self.line_ids.sudo().unlink()
        seen_codes, seen_names, values, new_categories = {}, {}, [], set()
        for number, row in rows:
            problems = []
            name = row.get('nombre', '')
            if not name:
                problems.append(_('falta el nombre'))
            key = normalize(name)
            if key and key in seen_names:
                problems.append(_('nombre repetido en la fila %s de la hoja', seen_names[key]))
            elif key:
                seen_names[key] = number
                if Product.search_count([('name', '=ilike', name)]):
                    problems.append(_('ya existe un producto con ese nombre en el programa'))

            code = row.get('codigo', '')
            if code:
                if not code.isalnum():
                    problems.append(_('el código solo puede llevar letras y números'))
                if code in seen_codes:
                    problems.append(_('código repetido en la fila %s de la hoja', seen_codes[code]))
                else:
                    seen_codes[code] = number
                    if Product.search_count(['|', ('barcode', '=', code), ('default_code', '=', code)]):
                        problems.append(_('ya hay un producto con ese código'))

            price = parse_number(row.get('precio_venta'))
            cost = parse_number(row.get('coste'))
            for label, amount in ((_('precio de venta'), price), (_('coste'), cost)):
                if amount is None:
                    problems.append(_('%s no es un número', label))
                elif amount < 0:
                    problems.append(_('%s negativo', label))
                elif not amount and not self.allow_zero_prices:
                    problems.append(_('%s a cero: revísalo o marca la casilla de abajo', label))

            vat = (row.get('iva') or '').replace('%', '').strip()
            vat = vat.split(',')[0].split('.')[0]
            tax = self.env['account.tax']
            if vat not in ALLOWED_VAT:
                problems.append(_('el IVA tiene que ser %s', ' / '.join(ALLOWED_VAT)))
            else:
                tax = taxes.get(vat)
                if not tax:
                    problems.append(_('la compañía no tiene configurado un IVA de venta del %s%%', vat))

            category_name = row.get('categoria', '')
            category = find_by_name(Category, category_name)
            if category_name and not category:
                if self.allow_new_categories:
                    new_categories.add(category_name)
                else:
                    problems.append(_('la categoría «%s» no existe', category_name))

            unit_name = row.get('unidad', '')
            uom = self._find_uom(unit_name) if unit_name else default_uom
            if unit_name and not uom:
                problems.append(_('la unidad «%s» no existe', unit_name))

            values.append({
                'import_id': self.id, 'row_number': number, 'code': code, 'name': name,
                'category_name': category_name, 'uom_id': uom.id if uom else False,
                'price': price or 0.0, 'cost': cost or 0.0, 'vat': vat if vat in ALLOWED_VAT else False,
                'tax_id': tax.id if tax else False,
                'message': '; '.join(problems) or _('correcto'),
                'has_error': bool(problems),
            })
        self.env['mgs.catalog.import.line'].sudo().create(values)
        errors = sum(1 for value in values if value['has_error'])
        notes = [_('%s filas leídas, %s con problemas.', len(values), errors)]
        if new_categories:
            notes.append(_('Se crearán estas categorías nuevas: %s.', ', '.join(sorted(new_categories))))
        if not errors:
            notes.append(_('Revisa la lista y pulsa «Importar catálogo». '
                           'Las existencias se registran después en Existencias iniciales.'))
        self.write({'error_count': errors, 'summary': '\n'.join(notes),
                    'state': 'draft' if errors else 'checked'})
        return {'type': 'ir.actions.act_window', 'name': _('Alta de catálogo'),
                'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}

    # ------------------------------------------------------------------
    # Alta
    # ------------------------------------------------------------------
    def action_apply(self):
        require_manager(self.env)
        self.ensure_one()
        if self.state == 'done':
            return True
        if self.state != 'checked' or not self.line_ids:
            raise UserError(_('Comprueba la hoja antes de importarla.'))
        if self.error_count or any(line.has_error for line in self.line_ids):
            raise UserError(_('Corrige la hoja: todavía hay filas con problemas.'))
        config = self.env['mgs.config']
        Category = self.env['product.category']
        default_category = self.env.ref('product.product_category_all')
        for line in self.line_ids:
            category = find_by_name(Category, line.category_name)
            if line.category_name and not category:
                if not self.allow_new_categories:
                    raise UserError(_('La categoría «%s» ya no existe. Vuelve a comprobar la hoja.',
                                      line.category_name))
                category = Category.create({'name': line.category_name})
            barcode = line.code or config.mgs_next_internal_barcode()
            template = self.env['product.template'].create({
                'name': line.name,
                'barcode': barcode,
                'categ_id': (category or default_category).id,
                'uom_id': line.uom_id.id or self.env.ref('uom.product_uom_unit').id,
                'list_price': line.price,
                'standard_price': line.cost,
                'taxes_id': [(6, 0, line.tax_id.ids)],
                # Mismos ajustes que da de alta la recepción: sin ellos el TPV no
                # sabría descontar partidas ni avisar de caducidades.
                'is_storable': True, 'sale_ok': True, 'available_in_pos': True,
                'tracking': 'lot', 'mgs_auto_lots': True, 'use_expiration_date': True,
            })
            line.sudo().write({'product_id': template.product_variant_id.id,
                               'code': barcode, 'message': _('creado')})
        self.write({'state': 'done',
                    'summary': _('%s productos creados. Ahora registra las existencias '
                                 'en Stock → Existencias iniciales y, si algún producto '
                                 'llevaba código interno, imprime su etiqueta.',
                                 len(self.line_ids))})
        return {'type': 'ir.actions.act_window', 'name': _('Alta de catálogo'),
                'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}

    def action_open_products(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Catálogo importado'),
                'res_model': 'product.template', 'view_mode': 'list,form',
                'domain': [('id', 'in', self.line_ids.product_id.product_tmpl_id.ids)]}


class CatalogImportLine(models.TransientModel):
    _name = 'mgs.catalog.import.line'
    _description = 'Fila del catálogo a importar'
    _order = 'row_number'

    import_id = fields.Many2one('mgs.catalog.import', required=True, ondelete='cascade')
    row_number = fields.Integer('Fila')
    code = fields.Char('Código')
    name = fields.Char('Nombre')
    category_name = fields.Char('Categoría')
    uom_id = fields.Many2one('uom.uom', 'Unidad')
    price = fields.Float('Precio de venta', digits='Product Price')
    cost = fields.Float('Coste', digits='Product Price')
    vat = fields.Char('IVA %')
    tax_id = fields.Many2one('account.tax', 'Impuesto')
    product_id = fields.Many2one('product.product', 'Producto creado', readonly=True)
    message = fields.Char('Comprobación', readonly=True)
    has_error = fields.Boolean(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('Las filas las genera la comprobación de la hoja.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_('Corrige la hoja y vuelve a comprobarla.'))
        return super().write(vals)
