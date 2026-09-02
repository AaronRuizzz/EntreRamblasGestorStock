/** @odoo-module **/
// Pone "Gestión de stock" como titulo base de la pestana del navegador.
// Al navegar, Odoo mostrara  "<Pantalla> - Gestión de stock".
import { registry } from "@web/core/registry";

registry.category("services").add("mgs_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "Gestión de stock" });
    },
});
