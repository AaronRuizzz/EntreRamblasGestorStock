/** @odoo-module **/
// Pone "Gestión de stock" como título base de la pestaña del navegador
// y limpia la barra superior eliminando elementos de chat y actividades
// para un uso directo y sin distracciones.
import { registry } from "@web/core/registry";

registry.category("services").add("mgs_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Gestión de stock" });
    },
});

// Eliminar iconos innecesarios de la barra superior (mensajería, actividades y llamadas)
const systray = registry.category("systray");
if (systray.contains("mail.messaging_menu")) {
    systray.remove("mail.messaging_menu");
}
if (systray.contains("mail.activity_menu")) {
    systray.remove("mail.activity_menu");
}
if (systray.contains("discuss.CallMenu")) {
    systray.remove("discuss.CallMenu");
}
