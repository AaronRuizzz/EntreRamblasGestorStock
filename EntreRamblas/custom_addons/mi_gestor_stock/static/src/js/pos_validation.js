/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc, RPCError } from "@web/core/network/rpc";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { serializeDateTime } from "@web/core/l10n/dates";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ask, makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { handleRPCError } from "@point_of_sale/app/errors/error_handlers";

patch(PosStore.prototype, {
    async mgsCheckStock(order = this.get_order()) {
        // De un ramo a medida hay que comprobar sus flores, no el ramo: el
        // producto de la composición no tiene existencias propias. Se manda el
        // contenido tal cual y el servidor lo valida (models/mgs_bouquet.py).
        const lines = order.lines.map(line => {
            const payload = { product_id: line.product_id.id, qty: line.qty };
            if (line.mgs_bouquet_spec) {
                payload.bouquet_spec = line.mgs_bouquet_spec;
            }
            return payload;
        });
        return rpc("/web/dataset/call_kw/pos.order/mgs_check_stock", {
            model: "pos.order", method: "mgs_check_stock",
            args: [this.session.id, lines, order.uuid],
            kwargs: {},
        });
    },
    async pay() {
        try {
            await this.mgsCheckStock();
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Revisar antes de cobrar"),
                body: error.data?.message || _t("No se puede comprobar el stock. Comprueba que el servidor local esté funcionando."),
            });
            return;
        }
        return super.pay(...arguments);
    },
});

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        let status;
        try {
            status = await this.pos.mgsCheckStock(this.currentOrder);
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("No se puede confirmar el cobro"),
                body: error.data?.message || _t("Comprueba la conexión con el servidor local. Si ya has cobrado, no repitas el pago."),
            });
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
            const accepted = await ask(this.dialog, {
                title: _t("Confirmar pago con tarjeta"),
                body: _t("Confirma que el datáfono ha aceptado el importe indicado. Registrar la tarjeta aquí no realiza el cobro en el terminal."),
                confirmLabel: _t("Pago aceptado"), cancelLabel: _t("Volver"),
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
            if (this.shouldDownloadInvoice() && order.is_to_invoice() && order.raw.account_move) {
                await this.invoiceService.downloadPdf(order.raw.account_move);
            }
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
        if (order.is_paid_with_cash() || order.get_change()) {
            await this.pos.mgsOpenSaleDrawer(order);
        }
        await this.afterOrderValidation();
    },
});
