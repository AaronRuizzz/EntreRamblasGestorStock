{
    "name": "Mi Gestor de Stock Personalizado",
    "version": "18.0.3.0.0",
    "summary": "Recepción, stock con avisos e informes para la floristería Entre Ramblas",
    "author": "aarm5719",
    "license": "LGPL-3",
    # Todas las apps del proyecto se declaran aqui como dependencia: asi
    # `-i mi_gestor_stock` sobre una BD vacia reproduce EXACTAMENTE el mismo
    # conjunto de modulos en cualquier equipo (ver bootstrap.ps1).
    "depends": [
        "stock",            # Inventario
        "product_expiry",   # Caducidad nativa por partida
        "barcodes",         # Motor de codigos de barras
        "web",
        "point_of_sale",    # TPV (sigue registrando las ventas; no esta en el menu)
        "contacts",         # Directorio de clientes/proveedores
        "l10n_es",          # Localizacion fiscal espanola (IVA, plan PYMEs, NIF)
    ],
    "data": [
        "security/mgs_security.xml",
        "security/ir.model.access.csv",
        "data/branding.xml",
        "data/mgs_access_data.xml",
        "data/cron_alerts.xml",
        "data/mgs_hardware_data.xml",
        "data/mgs_bouquet_data.xml",
        "data/mgs_event_data.xml",
        "views/mgs_config_views.xml",
        "views/mgs_hardware_job_views.xml",
        "views/mgs_reception_views.xml",
        "views/mgs_scrap_views.xml",
        "views/mgs_catalog_import_views.xml",
        "views/mgs_event_views.xml",
        "views/mgs_alert_views.xml",
        "views/mgs_dashboard_views.xml",
        "views/product_views.xml",
        "views/pos_report_views.xml",
        "views/mgs_pos_session_views.xml",
        "views/mgs_consumption_views.xml",
        "report/mgs_monthly_report.xml",
        "report/mgs_event_report.xml",
        "views/mgs_menus.xml",
        "views/mgs_security_views.xml",
        "views/login_templates.xml",
        "views/mgs_auth_templates.xml",
        "views/mgs_web_templates.xml",
        # ux_defaults va el ultimo: reapunta la salida del TPV a menu_mgs_root
        # y fija la pantalla de inicio al panel de Stock, ambas definidas antes.
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
            "mi_gestor_stock/static/src/js/navbar_active_section.js",
            "mi_gestor_stock/static/src/js/clean_form.js",
            "mi_gestor_stock/static/src/js/home.js",
            "mi_gestor_stock/static/src/js/home.xml",
            "mi_gestor_stock/static/src/js/stock_dashboard.js",
            "mi_gestor_stock/static/src/js/stock_dashboard.xml",
            "mi_gestor_stock/static/src/xml/mgs_errors.xml",
        ],
        "web.assets_frontend": [
            "mi_gestor_stock/static/src/scss/login.scss",
            "mi_gestor_stock/static/src/js/mgs_login.js",
        ],
        # Puente TPV <-> impresora termica ESC/POS y cajon portamonedas, sin
        # IoT Box (ver static/src/js/pos_hardware.js).
        "point_of_sale._assets_pos": [
            "mi_gestor_stock/static/src/scss/pos.scss",
            "mi_gestor_stock/static/src/js/pos_hardware.js",
            "mi_gestor_stock/static/src/js/pos_validation.js",
            "mi_gestor_stock/static/src/js/pos_bouquet.js",
            "mi_gestor_stock/static/src/js/pos_event_checkout.js",
            "mi_gestor_stock/static/src/xml/pos_bouquet.xml",
            "mi_gestor_stock/static/src/xml/pos_navbar.xml",
            "mi_gestor_stock/static/src/xml/pos_receipt.xml",
        ],
    },
    "installable": True,
    "application": True,
}
