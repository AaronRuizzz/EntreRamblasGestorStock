/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { parseFloat } from "@web/views/fields/parsers";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";

patch(OrderSummary.prototype, {
    // Botón "Eliminar" de cada línea (order_summary.xml, plantilla
    // pos_delete_line.xml): quita el producto de un solo clic, sin pasar
    // antes por cantidad 0. Solo en cuentas pendientes (sin cobrar): un
    // ticket ya pagado se corrige con una devolución, no borrando la línea.
    mgsDeleteLine(line) {
        if (line.order_id.finalized) {
            return;
        }
        const name = line.get_full_product_name();
        this.currentOrder.removeOrderline(line);
        this.pos.notification.add(_t("Línea eliminada: %s", name), { type: "success" });
    },

    // El numpad ya borra la línea al vaciar el buffer con retroceso
    // (_setValue("remove") cuando el buffer llega a null): eso no se toca.
    // Lo que falta es cuando se teclea el dígito «0» directamente como
    // cantidad: hoy deja la línea visible con cantidad 0 en vez de quitarla.
    // Las líneas de combo se dejan con su comportamiento nativo (los
    // gestiona `removeOrderline` como grupo si hiciera falta).
    _setValue(val) {
        if (val !== "remove" && this.pos.numpadMode === "quantity") {
            const selectedLine = this.currentOrder.get_selected_orderline();
            const parsed = typeof val === "number" ? val : parseFloat(val || "0");
            if (selectedLine && !selectedLine.combo_parent_id &&
                !selectedLine.combo_line_ids?.length && !isNaN(parsed) && parsed === 0) {
                return super._setValue("remove");
            }
        }
        return super._setValue(val);
    },
});
