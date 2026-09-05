/** @odoo-module **/
// Variante de formulario para las pantallas de trabajo (p. ej. Recepción), en las
// que los botones genéricos de Odoo (guardar en forma de nube, descartar, rueda
// de ajustes) no aportan nada y confunden: la pantalla tiene sus propios botones
// en la cabecera y es esa la única acción que importa.
//
// Solo añade una clase al raíz del formulario; el controlador de Odoo envuelve
// con ese `className` también al panel de control, así que desde SCSS se puede
// acotar el retoque a estas pantallas SIN ocultar nada de forma global
// (ver static/src/scss/backend.scss, sección "formularios de trabajo").
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";

export class MgsCleanFormController extends FormController {
    get className() {
        return { ...super.className, o_mgs_clean_form: true };
    }
}

registry.category("views").add("mgs_clean_form", {
    ...formView,
    Controller: MgsCleanFormController,
});
