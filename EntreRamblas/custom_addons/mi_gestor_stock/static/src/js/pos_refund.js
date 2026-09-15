/** @odoo-module **/
/**
 * Devoluciones guiadas.
 *
 * El núcleo de Odoo ya sabe devolver (TicketScreen: seleccionar líneas,
 * poner cantidad con el numpad, "Refund"); aquí solo se envuelve para que
 * sea guiado: "Devolver todo"/"Elegir productos", el importe visible antes
 * de continuar, y el botón relabeled a "Confirmar devolución". No se toca
 * la lógica de creación de la línea negativa ni lo que pasa después
 * (mgs_damaged_return.py, mgs_pos_stock.py): eso sigue exactamente igual.
 *
 * También vive aquí la simplificación de "Pedidos" a "Ventas y
 * devoluciones" con dos pestañas (Ventas en curso / Historial de tickets),
 * sobre los filtros nativos ACTIVE_ORDERS/SYNCED.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ask } from "@point_of_sale/app/store/make_awaitable_dialog";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";

patch(TicketScreen.prototype, {
    // -------- Devolver todo / Elegir productos --------
    refundAll(order) {
        for (const line of order.get_orderlines()) {
            const refundable = line.qty - line.refunded_qty;
            if (this.pos.isProductQtyZero(refundable)) {
                continue;
            }
            this.getToRefundDetail(line).qty = Math.abs(refundable);
        }
    },

    // "Elegir productos" no hace nada especial: deja el modo manual nativo
    // (tocar cada línea y poner la cantidad con el numpad), que ya es el
    // comportamiento por defecto de esta pantalla.
    mgsHasSelectableItems(order) {
        return !!order?.get_orderlines().some((line) =>
            !this.pos.isProductQtyZero(line.qty - line.refunded_qty));
    },

    mgsRefundAmount(order) {
        let total = 0;
        for (const detail of this._getRefundableDetails(order.get_partner(), order)) {
            const line = detail.line;
            if (!line || this.pos.isProductQtyZero(line.qty)) {
                continue;
            }
            total += Math.abs(line.price_subtotal_incl) * (detail.qty / Math.abs(line.qty));
        }
        return total;
    },

    async onDoRefund() {
        const order = this.getSelectedOrder();
        // Mismo camino que el nativo: en un ticket de un solo producto, la
        // línea a devolver se autoselecciona entera. Se repite aquí (antes
        // de calcular el importe) para que la confirmación también salga en
        // ese caso; super.onDoRefund() lo vuelve a llamar después sin
        // problema (ya queda puesto, no lo cambia dos veces).
        if (order && this._doesOrderHaveSoleItem(order)) {
            if (!this._prepareAutoRefundOnOrder(order)) {
                return;
            }
        }
        if (order && this.getHasItemsToRefund()) {
            const amount = this.mgsRefundAmount(order);
            const accepted = await ask(this.dialog, {
                title: _t("Confirmar devolución"),
                body: _t(
                    "Vas a devolver %(amount)s. ¿Confirmar la devolución?",
                    { amount: this.env.utils.formatCurrency(amount) }
                ),
                confirmLabel: _t("Confirmar devolución"),
                cancelLabel: _t("Volver"),
            });
            if (!accepted) {
                return;
            }
        }
        return super.onDoRefund(...arguments);
    },

    postRefund(destinationOrder) {
        // Para distinguir venta/devolución en "Ventas y devoluciones"
        // (pos_navbar.xml/getStatusLabel) sin depender solo del color.
        destinationOrder.uiState.mgsIsRefund = true;
        return super.postRefund(...arguments);
    },

    // -------- "Ventas y devoluciones": dos pestañas simplificadas --------
    get mgsSimplifiedTab() {
        return this.state.filter === "SYNCED" ? "history" : "ongoing";
    },

    mgsSetSimplifiedTab(tab) {
        this.onFilterSelected(tab === "history" ? "SYNCED" : "ACTIVE_ORDERS");
    },

    // Venta o devolución, con icono Y texto (no solo color): una devolución
    // es un pedido con alguna línea negativa vinculada a otra, o el que se
    // acaba de crear aquí mismo (postRefund).
    mgsIsRefundOrder(order) {
        return !!(order.uiState.mgsIsRefund ||
            order.lines.some((line) => line.qty < 0 && line.refunded_orderline_id));
    },

    mgsOrderKindLabel(order) {
        return this.mgsIsRefundOrder(order) ? _t("Devolución") : _t("Venta");
    },

    // "Venta de mostrador" es solo una etiqueta de presentación: nunca crea
    // ni enlaza un res.partner ficticio (por eso no se usa en get_partner_name
    // nativo, que otros sitios sí tratan como "sin cliente" válido).
    mgsPartnerDisplay(order) {
        return order.partner_id?.name || _t("Venta de mostrador");
    },
});
