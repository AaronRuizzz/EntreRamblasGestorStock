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
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

export class MgsCleanFormController extends FormController {
    get className() {
        return { ...super.className, o_mgs_clean_form: true };
    }
}

registry.category("views").add("mgs_clean_form", {
    ...formView,
    Controller: MgsCleanFormController,
});

// La configuración contiene ajustes que afectan a toda la tienda. A diferencia
// de las pantallas de trabajo, no se deben guardar por sorpresa al cambiar de
// menú: se pregunta claramente si se quieren conservar los cambios.
export class MgsConfigFormController extends MgsCleanFormController {
    async beforeLeave() {
        if (!(await this.model.root.isDirty()) || this.allowLeavingWithoutSaving) {
            return true;
        }
        return this._confirmSaveConfiguration();
    }

    async _confirmSaveConfiguration() {
        let canLeave = false;
        await new Promise((resolve) => {
            this.dialogService.add(ConfirmationDialog, {
                title: _t("Cambios sin guardar"),
                body: _t("Has cambiado la configuración. ¿Quieres guardar los cambios antes de salir?"),
                confirmLabel: _t("Guardar cambios"),
                cancelLabel: _t("No guardar"),
                confirm: async () => {
                    canLeave = await this.save({
                        reload: false,
                        onError: this.onSaveError.bind(this),
                    });
                    resolve();
                    // Si hay un error de validación, se mantiene el diálogo
                    // abierto y no se abandona la pantalla.
                    return canLeave;
                },
                cancel: async () => {
                    await this.discard();
                    canLeave = true;
                    resolve();
                },
                // Cerrar el aviso con la X, Escape o fuera de la ventana
                // equivale a continuar editando.
                dismiss: () => resolve(),
            });
        });
        return canLeave;
    }
}

registry.category("views").add("mgs_config_form", {
    ...formView,
    Controller: MgsConfigFormController,
});

// Mismo criterio para una lista-flujo (p. ej. Eventos y encargos): la rueda de
// «Acciones» del panel de control no aporta nada cuando la única acción es el
// botón propio de la cabecera. Solo añade una clase; el CSS acota el retoque.
export class MgsCleanListController extends ListController {
    get className() {
        return { ...super.className, o_mgs_clean_list: true };
    }
}

registry.category("views").add("mgs_clean_list", {
    ...listView,
    Controller: MgsCleanListController,
});
