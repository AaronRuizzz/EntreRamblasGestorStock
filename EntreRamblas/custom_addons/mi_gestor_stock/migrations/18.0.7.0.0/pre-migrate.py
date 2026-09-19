# -*- coding: utf-8 -*-
"""18.0.7.0.0 — se retiran «Informes personalizados» y la clasificación
«en B» (decisión de la propietaria: esos informes los lleva en una libreta
aparte, fuera del programa).

Desaparecen los modelos `mgs.report.template`, `mgs.report.preview.line`,
`mgs.report.sale.review`, `mgs.report.exclusion.log` y
`mgs.report.exclusion.wizard`, y los campos `pos.order.line.mgs_in_b` /
`mgs_report_excluded`. Odoo limpia solo, al final del `-u`, los `ir.model.data`
del módulo que no se vuelvan a tocar en esta actualización —eso ya retira las
vistas, acciones, menús, filas de `ir.model.access` y las entradas de
`ir.model`/`ir.model.fields` de los cinco modelos—, pero **nunca borra una
tabla ni una columna por su cuenta** (mismo motivo que ya documentó
18.0.4.0.0/post-migrate.py para los secretos del asistente de regeneración):
eso es lo que hace este script, antes de que el resto de la actualización
corra.

Irreversible: la copia de seguridad previa a esta actualización es la única
vuelta atrás para quien quisiera recuperar la clasificación «en B» o alguna
plantilla guardada.
"""
import logging

_logger = logging.getLogger(__name__)

TABLES = (
    "mgs_report_template",
    "mgs_report_preview_line",
    "mgs_report_sale_review",
    "mgs_report_exclusion_log",
    "mgs_report_exclusion_wizard",
)


def migrate(cr, version):
    if not version:
        return

    for table in TABLES:
        cr.execute("""
            SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = %s
        """, [table])
        if cr.fetchone():
            cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % table)
            _logger.info("mi_gestor_stock: tabla %s eliminada.", table)

    # Tablas many2many de mgs.report.template (category_ids, product_ids,
    # payment_method_ids): el nombre lo asigna Odoo solo a partir de los dos
    # modelos relacionados, así que se buscan por patrón en vez de adivinar
    # los tres nombres exactos.
    cr.execute("""
        SELECT table_name FROM information_schema.tables
         WHERE table_schema = 'public' AND table_name LIKE 'mgs_report_template_%_rel'
    """)
    for (rel_table,) in cr.fetchall():
        cr.execute('DROP TABLE IF EXISTS "%s" CASCADE' % rel_table)
        _logger.info("mi_gestor_stock: tabla de relación %s eliminada.", rel_table)

    for column in ("mgs_in_b", "mgs_report_excluded"):
        cr.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'pos_order_line' AND column_name = %s
        """, [column])
        if cr.fetchone():
            cr.execute('ALTER TABLE pos_order_line DROP COLUMN "%s"' % column)
            _logger.info("mi_gestor_stock: columna pos_order_line.%s eliminada.", column)

    _logger.info(
        "mi_gestor_stock: actualizado a 18.0.7.0.0 — «Informes personalizados» "
        "y la clasificación «en B» quedan retirados.")
