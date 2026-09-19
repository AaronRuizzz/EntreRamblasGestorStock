/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { RPCError } from "@web/core/network/rpc";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { serializeDateTime } from "@web/core/l10n/dates";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ask, makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { handleRPCError } from "@point_of_sale/app/errors/error_handlers";

patch(PosStore.prototype, {
    async pay() {
        // mgsCheckStock/mgsResolveDeficits: pos_stock_check.js. Antes de
        // cobrar se vuelve a comprobar todo el pedido por si algo cambió
        // desde el último chequeo interactivo (otra caja se llevó el último
        // lote, p. ej.); si falta algo sin autorizar, se pregunta aquí mismo.
        const result = await this.mgsResolveDeficits(this.get_order());
        if (!result.ok) {
            return;
        }
        return super.pay(...arguments);
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        const status = await this.pos.mgsResolveDeficits(this.currentOrder);
        if (!status.ok) {
            return;
        }
        if (!status.already_confirmed && this.currentOrder.state !== "paid") {
            for (const line of this.currentOrder.lines.filter(line => line.qty < 0 && line.product_id.is_storable)) {
                const condition = await makeAwaitable(this.dialog, SelectionPopup, {
                    title: _t("Estado de la devolución: %s", line.product_id.display_name),
                    list: [
                        { id: 1, label: _t("Recuperable: vuelve al stock"), item: "recoverable" },
                        { id: 2, label: _t("Deteriorada: registrar merma"), item: "damaged" },
                    ],
                });
                if (!condition) return;
                line.mgs_damaged_return = condition === "damaged";
            }
        }
        if (!status.already_confirmed && this.currentOrder.state !== "paid" &&
            this.paymentLines.some(line => line.amount !== 0 && !line.payment_method_id.is_cash_count)) {
            // Una devolución (línea con cantidad negativa) también se hace
            // en el datáfono, por separado: el texto lo recuerda en vez de
            // hablar de "cobro", que aquí sería confuso.
            const isRefund = this.currentOrder.lines.some(line => line.qty < 0);
            const accepted = await ask(this.dialog, {
                title: isRefund ? _t("Confirmar devolución con tarjeta") : _t("Confirmar pago con tarjeta"),
                body: isRefund
                    ? _t("Confirma que el datáfono ha aceptado la devolución. Recuerda hacer también la devolución en el datáfono: registrarla aquí no la hace en el terminal.")
                    : _t("Confirma que el datáfono ha aceptado el importe indicado. Registrar la tarjeta aquí no realiza el cobro en el terminal."),
                confirmLabel: isRefund ? _t("Devolución aceptada") : _t("Pago aceptado"), cancelLabel: _t("Volver"),
            });
            if (!accepted) return;
        }
        return super.validateOrder(isForceValidate);
    },

    // Odoo 18 avanza al ticket incluso al perder conexión. La tienda requiere
    // confirmación del servidor local: conservar el mismo UUID ante incertidumbre.
    async _finalizeValidation() {
        const order = this.currentOrder;
        if (order.state !== "paid") {
            order.date_order = serializeDateTime(luxon.DateTime.now());
            for (const line of [...this.paymentLines]) {
                if (line.amount === 0) order.remove_paymentline(line);
            }
        }
        this.pos.addPendingOrder([order.id]);
        order.state = "paid";
        this.ui.block();
        let saved;
        try {
            saved = await this.pos.syncAllOrders({ throw: true });
            if (!saved) throw new Error("No confirmation");
        } catch (error) {
            if (error instanceof RPCError) {
                order.state = "draft";
                handleRPCError(error, this.dialog);
            } else {
                this.dialog.add(AlertDialog, {
                    title: _t("Confirmación pendiente"),
                    body: _t("No se ha podido confirmar el resultado. No vuelvas a cobrar: restablece el servidor local y pulsa Validar para recuperar esta misma venta."),
                });
            }
            return;
        } finally {
            this.ui.unblock();
        }
        // La venta ya está confirmada en el servidor: a partir de aquí ni el
        // cajón ni la factura pueden abortar el resto del flujo. Antes, un
        // fallo al generar el PDF de la factura (dentro del mismo try que el
        // guardado) impedía llegar a abrir el cajón: pedir factura y pagar
        // en efectivo se quedaba con la caja cerrada.
        if (order.is_paid_with_cash() || order.get_change()) {
            await this.pos.mgsOpenSaleDrawer(order);
        }
        if (this.shouldDownloadInvoice() && order.is_to_invoice() && order.raw.account_move) {
            try {
                await this.invoiceService.downloadPdf(order.raw.account_move);
            } catch (error) {
                this.notification.add(
                    _t("Venta guardada y caja abierta. No se pudo generar el PDF de la factura: repítelo desde Facturación."),
                    { type: "warning", sticky: true }
                );
            }
        }
        await this.afterOrderValidation();
    },
});
