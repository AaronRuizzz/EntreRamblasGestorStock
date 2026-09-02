{
    "name": "Mi Gestor de Stock Personalizado",
    "version": "18.0.1.0.0",
    "summary": "Recepción, stock, compra e informes para la floristería Entre Ramblas",
    "author": "aarm5719",
    "license": "LGPL-3",
    # Todas las apps del proyecto se declaran aqui como dependencia: asi
    # `-i mi_gestor_stock` sobre una BD vacia reproduce EXACTAMENTE el mismo
    # conjunto de modulos en cualquier equipo (ver bootstrap.ps1).
    "depends": [
        "stock",            # Inventario
        "barcodes",         # Motor de codigos de barras
        "web",
        "point_of_sale",    # TPV
        "contacts",         # Directorio de clientes/proveedores
        "l10n_es",          # Localizacion fiscal espanola (IVA, plan PYMEs, NIF)
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/branding.xml",
        "data/cron_alerts.xml",
        "views/mgs_reception_views.xml",
        "views/product_views.xml",
        "views/pos_report_views.xml",
        "views/mgs_menus.xml",
        "views/login_templates.xml",
        # ux_defaults va el ultimo: reapunta la salida del TPV a menu_mgs_root
        # y fija la pantalla de inicio a action_mgs_products, ambas definidas
        # en mgs_menus.xml.
        "data/ux_defaults.xml",
    ],
    "assets": {
        # Color de marca de Odoo (azul pizarra). 'prepend' para ganar a los
        # `!default` de web/primary_variables.scss. Afecta a TODOS los bundles.
        "web._assets_primary_variables": [
            ("prepend", "mi_gestor_stock/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "mi_gestor_stock/static/src/scss/backend.scss",
            "mi_gestor_stock/static/src/js/title.js",
        ],
        "web.assets_frontend": [
            "mi_gestor_stock/static/src/scss/login.scss",
        ],
    },
    "installable": True,
    "application": True,
}
