/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { parseFloat } from "@web/views/fields/parsers";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { enhancedButtons } from "@point_of_sale/app/generic_components/numpad/numpad";
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

    // Botón "Cantidad" de cada línea (mismo sitio que "Eliminar"): abre el
    // teclado numérico de siempre (el que ya usa "Fijar nueva cantidad" al
    // decrecer, con los mismos botones de enhancedButtons()) para escribir
    // la cantidad de un tirón en vez de tocar +1 treinta veces.
    async mgsEditQuantity(line) {
        if (line.order_id.finalized || line.combo_parent_id || line.combo_line_ids?.length) {
            return;
        }
        const inputNumber = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Cantidad"),
            startingValue: line.get_quantity(),
            buttons: await this._getShowDecreaseQuantityPopupButtons(),
        });
        if (inputNumber === undefined || inputNumber === "") {
            return;
        }
        const parsed = parseFloat(inputNumber);
        if (isNaN(parsed)) {
            return;
        }
        if (parsed === 0) {
            this.currentOrder.removeOrderline(line);
            return;
        }
        const result = line.set_quantity(parsed);
        if (result !== true) {
            this.dialog.add(AlertDialog, result);
        }
    },

    // El numpad ya borra la línea al vaciar el buffer con retroceso
    // (_setValue("remove") cuando el buffer llega a null). La flecha roja
    // (Backspace) quitaba las 3 unidades de una tacada en vez de una a una:
    // con cantidad > 1 se resta 1 y se queda en la línea; con 1 o menos
    // (o para combos/propinas, que llevan su propio comportamiento) se deja
    // pasar al borrado nativo de toda la línea.
    // Lo que falta aparte es cuando se teclea el dígito «0» directamente
    // como cantidad: hoy deja la línea visible con cantidad 0 en vez de
    // quitarla. Las líneas de combo se dejan con su comportamiento nativo
    // (los gestiona `removeOrderline` como grupo si hiciera falta).
    _setValue(val) {
        if (val === "remove" && this.pos.numpadMode === "quantity") {
            const selectedLine = this.currentOrder.get_selected_orderline();
            if (selectedLine && !selectedLine.combo_parent_id &&
                !selectedLine.combo_line_ids?.length && !selectedLine.isTipLine?.()) {
                const qty = selectedLine.get_quantity();
                if (Math.abs(qty) > 1) {
                    const result = selectedLine.set_quantity(qty - Math.sign(qty));
                    if (result !== true) {
                        this.dialog.add(AlertDialog, result);
                        this.numberBuffer.reset();
                    }
                    return;
                }
            }
        }
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
