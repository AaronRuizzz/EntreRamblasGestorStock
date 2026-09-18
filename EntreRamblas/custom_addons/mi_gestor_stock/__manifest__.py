{
    "name": "Mi Gestor de Stock Personalizado",
    "version": "18.0.6.0.2",
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
        "data/mgs_report_template_data.xml",
        "data/mgs_correction_data.xml",
        # Los informes (ir.actions.report) van ANTES que cualquier vista: la
        # cabecera del formulario de evento referencia %(action_report_mgs_event)d
        # y una instalacion sobre BD vacia fallaba con "External ID not found"
        # porque la vista se cargaba antes que su accion de informe.
        "report/mgs_monthly_report.xml",
        "report/mgs_event_report.xml",
        "report/mgs_report_builder.xml",
        "report/pos_order_receipt_report.xml",
        "views/mgs_config_views.xml",
        "views/mgs_hardware_job_views.xml",
        "views/mgs_reception_views.xml",
        "views/mgs_scrap_views.xml",
        "views/mgs_catalog_import_views.xml",
        "views/mgs_event_views.xml",
        "views/mgs_alert_views.xml",
        "views/mgs_dashboard_views.xml",
        "views/mgs_stock_ledger_views.xml",
        "views/product_views.xml",
        "views/pos_report_views.xml",
        "views/mgs_pos_session_views.xml",
        "views/mgs_consumption_views.xml",
        # Antes de mgs_menus.xml: los menús nuevos referencian sus acciones
        # (action_mgs_report_templates, action_mgs_corrections) por ID.
        "views/mgs_report_template_views.xml",
        "views/mgs_report_exclusion_views.xml",
        "views/mgs_correction_views.xml",
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
            "mi_gestor_stock/static/src/js/stock_ledger.js",
            "mi_gestor_stock/static/src/js/stock_ledger.xml",
            "mi_gestor_stock/static/src/js/mgs_category_widget.js",
            "mi_gestor_stock/static/src/xml/mgs_category_widget.xml",
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
            "mi_gestor_stock/static/src/js/pos_catalog_refresh.js",
            "mi_gestor_stock/static/src/js/pos_validation.js",
            "mi_gestor_stock/static/src/js/pos_bouquet.js",
            "mi_gestor_stock/static/src/js/pos_event_checkout.js",
            # pos_stock_check.js define mgsResolveDeficits, que usan tanto
            # pos_validation.js (pay/validateOrder) como el propio archivo
            # (addProductToOrder/clickLine): el orden de carga entre módulos
            # JS independientes no importa para los patch() de Owl (todos se
            # aplican antes de que el TPV arranque), solo que estén todos.
            "mi_gestor_stock/static/src/js/pos_stock_check.js",
            "mi_gestor_stock/static/src/js/pos_delete_line.js",
            "mi_gestor_stock/static/src/js/pos_refund.js",
            "mi_gestor_stock/static/src/js/pos_partner_delete.js",
            "mi_gestor_stock/static/src/xml/pos_bouquet.xml",
            "mi_gestor_stock/static/src/xml/pos_navbar.xml",
            "mi_gestor_stock/static/src/xml/pos_refund.xml",
            "mi_gestor_stock/static/src/xml/pos_partner.xml",
            "mi_gestor_stock/static/src/xml/pos_receipt.xml",
            "mi_gestor_stock/static/src/xml/pos_stock_banner.xml",
            "mi_gestor_stock/static/src/xml/pos_delete_line.xml",
        ],
        # Tours de navegador (odoo.tests HttpCase.start_tour) — solo se
        # cargan en modo test (--test-enable), nunca en producción.
        "web.assets_tests": [
            "mi_gestor_stock/static/tests/tours/**/*",
        ],
    },
    "installable": True,
    "application": True,
}
