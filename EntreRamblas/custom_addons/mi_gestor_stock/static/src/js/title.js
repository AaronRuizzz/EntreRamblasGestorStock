/** @odoo-module **/
// Pone "Gestión de stock" como título base de la pestaña del navegador
// y limpia la barra superior eliminando elementos de chat y actividades
// para un uso directo y sin distracciones.
import { registry } from "@web/core/registry";
import { NavBar } from "@web/webclient/navbar/navbar";
import { patch } from "@web/core/utils/patch";

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

// ------------------------------------------------------------
// Optimización de la barra de navegación (NavBar):
// Cuando una sección del menú en el navbar solo tenga 1 elemento/acción,
// no debe aparecer la lista con opciones (desplegable innecesario),
// sino actuar como botón directo de navegación.
// En cambio, si tiene más de 1 elemento, sí debe aparecer el desplegable con sus opciones.
// ------------------------------------------------------------

function getLeafMenuItems(menu) {
    if (!menu.childrenTree || menu.childrenTree.length === 0) {
        return (menu.actionID || menu.actionPath) ? [menu] : [];
    }
    const leaves = [];
    for (const child of menu.childrenTree) {
        leaves.push(...getLeafMenuItems(child));
    }
    return leaves;
}

patch(NavBar.prototype, {
    get currentAppSections() {
        const sections = super.currentAppSections;
        if (!sections || !sections.length) {
            return sections;
        }
        return sections.map((section) => {
            const leaves = getLeafMenuItems(section);
            // Si la sección solo tiene exactamente 1 elemento de acción final:
            if (leaves.length === 1) {
                const singleLeaf = leaves[0];
                return {
                    ...singleLeaf,
                    id: section.id,
                    name: section.name,
                    xmlid: section.xmlid,
                    childrenTree: [], // Al no tener hijos, navbar.xml lo renderiza como botón directo, sin dropdown
                };
            }
            // Si tiene más de 1 elemento, se conserva como desplegable con todas sus opciones
            return section;
        });
    },
    set currentAppSections(_) {},
});
