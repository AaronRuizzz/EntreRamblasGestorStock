/** @odoo-module **/
// Pone "Gestión de stock" como título base de la pestaña del navegador y
// quita del systray y del menú de usuario lo que no pinta nada en una
// tienda de dos personas: chat interno, llamadas, el reloj de
// actividades (nunca hay ninguna: el addon no crea mail.activity en
// ningún sitio; los avisos de stock reales van por mgs.stock.alert y ya
// se ven en el Panel y en Alertas) y los enlaces a odoo.com.
import { registry } from "@web/core/registry";

registry.category("services").add("mgs_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Gestión de stock" });
    },
});

const systray = registry.category("systray");
for (const key of ["mail.messaging_menu", "discuss.CallMenu", "mail.activity_menu"]) {
    if (systray.contains(key)) {
        systray.remove(key);
    }
}

const userMenu = registry.category("user_menuitems");
for (const key of ["documentation", "support", "odoo_account", "install_pwa"]) {
    if (userMenu.contains(key)) {
        userMenu.remove(key);
    }
}
