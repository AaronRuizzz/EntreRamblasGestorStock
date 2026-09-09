/** @odoo-module **/
// Pone "Gestión de stock" como título base de la pestaña del navegador y
// quita del systray, del menú de usuario y del engranaje de las listas lo
// que no pinta nada en un gestor de floristería: chat interno, llamadas, el
// reloj de actividades (nunca hay ninguna: el addon no crea mail.activity en
// ningún sitio; los avisos de stock reales van por mgs.stock.alert y ya se
// ven en el Panel y en Alertas), los enlaces a odoo.com, el buscador de
// comandos, la ficha completa de Preferencias, el interruptor de tours
// guiados e «Importar registros» (para eso está «Alta de catálogo», que sí
// valida). Del menú de usuario solo quedan «Cambiar contraseña» y «Cerrar
// sesión».
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

registry.category("services").add("mgs_title", {
    // Depende de "tour_service" solo por el ORDEN de arranque: ese servicio
    // registra su entrada "web_tour.tour_enabled" (el interruptor
    // "Onboarding") DENTRO de su propio start(), no al cargar el módulo, así
    // que hay que esperar a que termine de arrancar para poder quitarla.
    dependencies: ["title", "tour_service"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Gestión de stock" });

        const systray = registry.category("systray");
        for (const key of ["mail.messaging_menu", "discuss.CallMenu", "mail.activity_menu"]) {
            if (systray.contains(key)) {
                systray.remove(key);
            }
        }

        const userMenu = registry.category("user_menuitems");
        for (const key of [
            "documentation", "support", "odoo_account", "install_pwa",
            "shortcuts", "profile", "web_tour.tour_enabled",
            "separator", // sin nada por encima que dividir, quedaría huérfano
        ]) {
            if (userMenu.contains(key)) {
                userMenu.remove(key);
            }
        }
        userMenu.add("mgs_change_password", () => ({
            type: "item",
            id: "mgs_change_password",
            description: "Cambiar contraseña",
            callback: async () => {
                const action = await env.services.orm.call(
                    "res.users", "preference_change_password", [[user.userId]]);
                env.services.action.doAction(action);
            },
            sequence: 55,
        }));

        const cogMenu = registry.category("cogMenu");
        if (cogMenu.contains("import-menu")) {
            cogMenu.remove("import-menu");
        }
    },
});
