/** @odoo-module **/
/**
 * Resalta en la barra superior la sección en la que estás.
 *
 * Odoo 18 Community no marca la sección activa de la navbar: su router solo
 * guarda la "app" actual (aquí siempre "Gestor de Stock"), no la sección
 * dentro de ella, y la NavBar NO se vuelve a renderizar al cambiar de sección
 * dentro de la misma app. Sin esto, entrar en Stock, Mermas o Informes no se
 * nota: los tres se ven igual.
 *
 * No se hereda la plantilla (web.NavBar.SectionsMenu usa un dict `attrs` y
 * DropdownGroup, frágil de parchear entre versiones menores). En su lugar se
 * escucha el bus `ACTION_MANAGER:UI-UPDATED` —que sí salta en cada cambio de
 * acción— y se marca en el DOM la sección cuya acción está abierta: el core ya
 * pone `data-section` con el id de la sección en `.o_menu_sections`. La clase
 * la estiliza backend.scss.
 */
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useBus } from "@web/core/utils/hooks";
import { useEffect } from "@odoo/owl";

patch(NavBar.prototype, {
    setup() {
        super.setup();
        // En cada cambio de acción y tras cada render (el segundo cubre el
        // primer pintado y los reajustes de ancho de la propia navbar).
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this._mgsMarkActiveSection());
        useEffect(() => this._mgsMarkActiveSection());
    },

    /**
     * Id de la sección de primer nivel cuya acción —o la de alguno de sus
     * hijos— es la que está abierta ahora mismo. `null` si no hay ninguna
     * (la página de inicio, por ejemplo).
     */
    _mgsActiveSectionId() {
        const controller = this.actionService.currentController;
        const action = controller && controller.action;
        if (!action) {
            return null;
        }
        const matches = (node) => {
            if (node.actionID && (node.actionID === action.id || node.actionID === action.xmlid)) {
                return true;
            }
            return (node.childrenTree || []).some(matches);
        };
        for (const section of this.currentAppSections) {
            if (matches(section)) {
                return section.id;
            }
        }
        return null;
    },

    _mgsMarkActiveSection() {
        const root = this.appSubMenus && this.appSubMenus.el;
        if (!root) {
            return;
        }
        const activeId = this._mgsActiveSectionId();
        for (const el of root.querySelectorAll("[data-section]")) {
            const isActive = activeId !== null && String(activeId) === el.dataset.section;
            // En los desplegables el data-section está en un <span> interno;
            // la clase tiene que ir en el botón/enlace clicable.
            const target = el.closest(".o_nav_entry, .dropdown-toggle") || el;
            target.classList.toggle("o_mgs_active_section", isActive);
        }
    },
});
