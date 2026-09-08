"""Informe mensual largo: muchas mermas, nombres largos y varias páginas.

El PDF corto ya estaba comprobado; faltaba ver qué pasa cuando el mes trae mucha
merma y nombres que no caben en una línea. Aquí se monta un mes sintético dentro
de UNA transacción que nunca se confirma: la base de validación queda intacta.

Requiere el servidor HTTP de pruebas en 8075 (wkhtmltopdf descarga de ahí los
estilos) y el wkhtmltopdf portátil de `install-pdf.ps1`.
"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ['PATH'] = str(root / '.odoo_data/wkhtmltox/bin') + os.pathsep + os.environ['PATH']
sys.path.insert(0, str(root / 'odoo'))
import odoo
from odoo import api, fields, SUPERUSER_ID
from odoo.modules.registry import Registry

odoo.tools.config.parse_config(['-c', str(root / 'odoo.conf'), '--db_host=127.0.0.1',
    '--db_port=55432', '--db_user=mgs_test', '-d', 'mgs_validation'])

PRODUCTS = 45
LONG_NAME = ('Composición de temporada con rosa roja de tallo largo, eucalipto '
             'cinerea, paniculata blanca y papel kraft reciclado número %s')

registry = Registry('mgs_validation')
with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {'lang': 'es_ES', 'tz': 'Europe/Madrid'})
    params = env['ir.config_parameter']
    previous = params.get_param('report.url')
    params.set_param('report.url', 'http://127.0.0.1:8075')
    cr.commit()  # wkhtmltopdf entra por HTTP: necesita ver report.url ya escrito.
    try:
        warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)
        stock = warehouse.lot_stock_id
        created = env['product.product']
        for index in range(PRODUCTS):
            product = env['product.product'].create({
                'name': LONG_NAME % index, 'is_storable': True, 'tracking': 'lot',
                'mgs_auto_lots': True, 'use_expiration_date': True,
                'list_price': 3.5 + index, 'standard_price': 1.25 + index,
            })
            created |= product
            lot = env['stock.lot'].create({
                'name': 'PDF-%s' % index, 'product_id': product.id, 'company_id': env.company.id,
                'expiration_date': False, 'mgs_unit_cost': 1.25 + index, 'mgs_cost_recorded': True,
            })
            quant = env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product.id, 'location_id': stock.id, 'lot_id': lot.id,
                'inventory_quantity': 30,
            })
            quant._apply_inventory()
            scrap = env['stock.scrap'].create({
                'product_id': product.id, 'lot_id': lot.id, 'scrap_qty': 3,
                'product_uom_id': product.uom_id.id, 'location_id': stock.id,
                'company_id': env.company.id, 'mgs_reason': 'deterioration',
            })
            scrap.do_scrap()

        report = env['mgs.monthly.report'].create({})
        data = report.mgs_get_report_data()
        assert len(data['scrap_rows']) >= PRODUCTS, 'Faltan mermas en el informe'
        assert len(data['stock_rows']) >= PRODUCTS, 'Faltan filas de stock en el informe'
        pdf, kind = env['ir.actions.report']._render_qweb_pdf(
            'mi_gestor_stock.action_report_mgs_monthly', [report.id])
        assert kind == 'pdf' and pdf.startswith(b'%PDF-'), 'No se ha generado un PDF real'

        from PyPDF2 import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf))
        pages = len(reader.pages)
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        assert pages >= 3, 'Se esperaban varias páginas y solo hay %s' % pages
        # El nombre largo tiene que aparecer entero, no cortado por el ancho del A4.
        assert 'papel kraft reciclado' in text.replace('\n', ' '), 'El nombre largo se ha perdido'
        assert 'Detalle de mermas' in text and 'Stock restante' in text, 'Faltan apartados del informe'
        # Ninguna página en blanco: síntoma clásico de tabla que se desborda.
        empty = [n for n, page in enumerate(reader.pages, 1) if not (page.extract_text() or '').strip()]
        assert not empty, 'Páginas en blanco: %s' % empty
        target = root / '.odoo_data/output/pdf/informe-validacion-largo.pdf'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf)
        print('OK PDF largo: %s páginas, %s mermas, %s filas de stock -> %s'
              % (pages, len(data['scrap_rows']), len(data['stock_rows']), target))
    finally:
        cr.rollback()  # Ni productos, ni mermas, ni existencias sintéticas.
        params.set_param('report.url', previous or False)
        cr.commit()
print('OK: la base de validación queda sin el mes sintético')
