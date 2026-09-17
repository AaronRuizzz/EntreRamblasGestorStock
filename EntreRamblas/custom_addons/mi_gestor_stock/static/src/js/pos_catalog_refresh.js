/** @odoo-module **/
/**
 * La caja carga el catálogo al abrirse. Una recepción posterior ya crea el
 * producto con `available_in_pos`, pero la parrilla de una sesión abierta no
 * conoce ese registro hasta que se vuelve a cargar el cliente.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Navbar } from "@point_of_sale/app/navbar/navbar";

patch(Navbar.prototype, {
    mgsRefreshCatalog() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Actualizar productos"),
            body: _t("La caja recargará el catálogo y mostrará el stock recibido. La venta actual se conserva."),
            confirmLabel: _t("Actualizar ahora"),
            cancelLabel: _t("Cancelar"),
            confirm: () => window.location.reload(),
        });
    },
});
