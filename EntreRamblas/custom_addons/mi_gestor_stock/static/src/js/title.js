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
import { patch } from "@web/core/utils/patch";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

// Menú de usuario: en lugar de ir quitando entradas en un start() (que compite
// con CUÁNDO las registra cada módulo — el interruptor de tours, por ejemplo,
// se añade dentro del start() de su propio servicio), se FILTRA al construir
// el menú. `getElements` corre en cada apertura, así que da igual el orden de
// arranque: solo sobreviven «Cambiar contraseña» y «Cerrar sesión».
const ALLOWED_USER_MENU_IDS = new Set(["mgs_change_password", "logout"]);

patch(UserMenu.prototype, {
    getElements() {
        return super.getElements().filter((el) => ALLOWED_USER_MENU_IDS.has(el.id));
    },
});

registry.category("user_menuitems").add("mgs_change_password", (env) => ({
    type: "item",
    id: "mgs_change_password",
    description: "Cambiar contraseña",
    callback: async () => {
        const action = await env.services.orm.call(
            "res.users", "preference_change_password", [[user.userId]]);
        env.services.action.doAction(action);
    },
    sequence: 10,
}));

registry.category("services").add("mgs_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Gestión de stock" });

        const systray = registry.category("systray");
        for (const key of ["mail.messaging_menu", "discuss.CallMenu", "mail.activity_menu"]) {
            if (systray.contains(key)) {
                systray.remove(key);
            }
        }

        const cogMenu = registry.category("cogMenu");
        if (cogMenu.contains("import-menu")) {
            cogMenu.remove("import-menu");
        }
    },
});
