"""Genera el PDF nativo Odoo sobre la base aislada; requiere servidor en 8075."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
os.environ['PATH'] = str(root / '.odoo_data/wkhtmltox/bin') + os.pathsep + os.environ['PATH']
sys.path.insert(0, str(root / 'odoo'))
import odoo
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

odoo.tools.config.parse_config(['-c', str(root / 'odoo.conf'), '--db_host=127.0.0.1',
    '--db_port=55432', '--db_user=mgs_test', '-d', 'mgs_validation'])
with Registry('mgs_validation').cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {'lang': 'es_ES', 'tz': 'Europe/Madrid'})
    params = env['ir.config_parameter']
    previous = params.get_param('report.url')
    params.set_param('report.url', 'http://127.0.0.1:8075')
    report = env['mgs.monthly.report'].create({})
    cr.commit()
    try:
        pdf, kind = env['ir.actions.report']._render_qweb_pdf(
            'mi_gestor_stock.action_report_mgs_monthly', [report.id])
        assert kind == 'pdf' and pdf.startswith(b'%PDF-'), 'No se ha generado un PDF real'
        target = root / '.odoo_data/output/pdf/informe-validacion.pdf'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf)
        print('PDF generado:', target)
    finally:
        params.set_param('report.url', previous or False)
        report.unlink()
        cr.commit()
