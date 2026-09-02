{
    "name": "Mi Gestor de Stock Personalizado",
    "version": "18.0.1.0.0",
    "summary": "Personalizaciones de inventario, punto de venta y marca Entre Ramblas",
    "author": "aarm5719",
    "license": "LGPL-3",
    "depends": ["stock", "barcodes", "web", "point_of_sale"],
    "data": [
        "data/branding.xml",
        "data/ux_defaults.xml",
        "views/stock_picking_views.xml",
        "views/login_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mi_gestor_stock/static/src/scss/custom_style.scss",
            "mi_gestor_stock/static/src/scss/backend.scss",
            "mi_gestor_stock/static/src/js/title.js",
        ],
        "web.assets_frontend": [
            "mi_gestor_stock/static/src/scss/login.scss",
        ],
    },
    "installable": True,
    "application": False,
}
