/** @odoo-module **/
/**
 * Resalta en la barra superior la sección en la que estás.
 *
 * Odoo 18 Community no marca la sección activa de la navbar: su router solo
 * guarda la "app" actual (aquí siempre "Gestor de Stock"), no la sección
 * dentro de ella. Sin esto, entrar en Stock, Mermas o Informes no se nota:
 * los tres se ven igual.
 *
 * No se hereda la plantilla (web.NavBar.SectionsMenu usa un dict `attrs` y
 * DropdownGroup, frágil de parchear entre versiones menores). En su lugar,
 * tras cada render se recorre `.o_menu_sections [data-section]` —el core ya
 * pone ese data-attr con el id de la sección— y se marca la que corresponde
 * a la acción abierta. La clase la estiliza backend.scss.
 */
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { useEffect } from "@odoo/owl";

patch(NavBar.prototype, {
    setup() {
        super.setup();
        useEffect(() => this._mgsMarkActiveSection());
    },

    /**
     * Id de la sección de primer nivel cuya acción —o la de alguno de sus
     * hijos— es la que está abierta ahora mismo. `null` si no hay ninguna
     * (la página de inicio, por ejemplo).
     */
    _mgsActiveSectionId() {
        const actionId = this.actionService.currentController?.action?.id;
        if (!actionId) {
            return null;
        }
        const matches = (node) =>
            node.actionID === actionId ||
            (node.childrenTree || []).some(matches);
        for (const section of this.currentAppSections) {
            if (matches(section)) {
                return section.id;
            }
        }
        return null;
    },

    _mgsMarkActiveSection() {
        const root = this.appSubMenus?.el;
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
