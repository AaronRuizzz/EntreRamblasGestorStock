/** @odoo-module **/
/**
 * Botón "Eliminar cliente" en el desplegable de cada fila del selector de
 * clientes del TPV (plantilla en pos_partner.xml). El servidor decide si
 * borra de verdad o archiva (res_partner.py:mgs_pos_delete) según el
 * cliente tenga ventas/encargos; aquí solo se confirma, se llama y se
 * refresca la lista local.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ask } from "@point_of_sale/app/store/make_awaitable_dialog";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";

patch(PartnerLine.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
        this.dialog = useService("dialog");
    },

    async mgsDeletePartner(partner) {
        const confirmed = await ask(this.dialog, {
            title: _t("Eliminar cliente"),
            body: _t(
                "¿Eliminar a %s? Si tiene ventas o encargos asociados no se puede " +
                "eliminar: se archivará en su lugar (dejará de aparecer en las listas).",
                partner.name
            ),
        });
        if (!confirmed) {
            return;
        }
        let result;
        try {
            result = await this.pos.data.call("res.partner", "mgs_pos_delete", [[partner.id]]);
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("No se pudo completar la operación"),
                body: error?.data?.message || _t("Inténtalo de nuevo."),
            });
            return;
        }
        // El servidor ya ha borrado o archivado de verdad: en ambos casos
        // el cliente debe desaparecer de la lista local del TPV.
        this.pos.models["res.partner"].get(partner.id)?.delete();
        this.pos.notification.add(result.message, { type: "success" });
    },
});
