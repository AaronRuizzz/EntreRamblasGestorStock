/** @odoo-module **/
// Pone "Gestión de stock" como título base de la pestaña del navegador
// y quita del systray lo que no se usa (chat interno y llamadas). El
// reloj de actividades (mail.activity_menu) se conserva a propósito:
// es el contador nativo que avisa de los productos bajo stock mínimo
// (ver models/product_template.py::_mgs_cron_stock_alerts).
import { registry } from "@web/core/registry";

registry.category("services").add("mgs_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Gestión de stock" });
    },
});

const systray = registry.category("systray");
if (systray.contains("mail.messaging_menu")) {
    systray.remove("mail.messaging_menu");
}
if (systray.contains("discuss.CallMenu")) {
    systray.remove("discuss.CallMenu");
}
