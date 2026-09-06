/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { HardwareProxy } from "@point_of_sale/app/hardware_proxy/hardware_proxy_service";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ProductProduct } from "@point_of_sale/app/models/product_product";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { ask, makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";
import { TextInputPopup } from "@point_of_sale/app/utils/input_popups/text_input_popup";

async function mgsCall(method, args = []) {
    return rpc(`/web/dataset/call_kw/mgs.config/${method}`, {
        model: "mgs.config", method, args, kwargs: {},
    }, { silent: true });
}

patch(ProductProduct.prototype, {
    isTracked() { return this.mgs_auto_lots ? false : super.isTracked(...arguments); },
});
patch(PosOrderline.prototype, {
    has_valid_product_lot() {
        return this.product_id.mgs_auto_lots || super.has_valid_product_lot(...arguments);
    },
});

patch(HardwareProxy.prototype, {
    async openCashbox(action = false) {
        const reason = await makeAwaitable(this.pos.dialog, TextInputPopup, {
            title: _t("Motivo de apertura del cajón"),
            startingValue: typeof action === "string" ? action : "",
            placeholder: _t("Ej.: preparar cambio o contar efectivo"),
        });
        if (!reason?.trim()) return;
        try {
            const job = await mgsCall("mgs_pos_manual_drawer", [this.pos.session.id, reason.trim(), crypto.randomUUID()]);
            await this.pos.mgsHardwareStatus(job);
        } catch (error) {
            this.pos.notification.add(error.data?.message || _t("No se pudo confirmar la apertura. Comprueba el cajón antes de repetirla."), { type: "warning", sticky: true });
        }
    },
});

patch(PosStore.prototype, {
    async processServerData() {
        const result = await super.processServerData(...arguments);
        this.mgsHardware = { escpos_receipt: false, drawer: false };
        try {
            this.mgsHardware = await mgsCall("mgs_pos_hardware_info");
        } catch (error) {
            this.notification.add(_t("No se pudo consultar la configuración de la impresora."), { type: "warning" });
        }
        return result;
    },
    async mgsHardwareStatus(job) {
        if (job.state === "disabled") return job;
        const status = await mgsCall("mgs_pos_job_status", [job.id]);
        if (status.state !== "sent") {
            this.notification.add(_t("Solicitud registrada. El envío no está confirmado: comprueba el dispositivo antes de repetirlo."), { type: "warning", sticky: true });
        }
        return status;
    },
    async mgsOpenSaleDrawer(order) {
        if (!this.mgsHardware?.drawer) return;
        try {
            const job = await mgsCall("mgs_pos_open_drawer", [order.id]);
            await this.mgsHardwareStatus(job);
        } catch (error) {
            this.notification.add(_t("Venta guardada. No se pudo confirmar la apertura del cajón."), { type: "warning", sticky: true });
        }
    },
    async printReceipt(options = {}) {
        const order = options.order || this.get_order();
        if (!this.mgsHardware?.escpos_receipt || options.printBillActionTriggered) {
            return super.printReceipt(options);
        }
        if (typeof order?.id !== "number") {
            this.notification.add(_t("Confirma la venta en el servidor antes de imprimir."), { type: "warning" });
            return false;
        }
        try {
            let job = await mgsCall("mgs_pos_print_order", [order.id]);
            if (job.existing && !options.order) {
                const confirmed = await ask(this.dialog, {
                    title: _t("Reimprimir ticket"),
                    body: _t("Ya existe una solicitud para esta venta. Comprueba la impresora y confirma si necesitas otra copia."),
                    confirmLabel: _t("Imprimir otra copia"), cancelLabel: _t("Cancelar"),
                });
                if (!confirmed) return false;
                job = await mgsCall("mgs_pos_print_order", [order.id, crypto.randomUUID()]);
            }
            const status = await this.mgsHardwareStatus(job);
            if (status.state === "sent") {
                order.nb_print = status.nb_print;
                return true;
            }
        } catch (error) {
            this.notification.add(error.data?.message || _t("Venta guardada. Resultado de impresión incierto: comprueba el papel antes de solicitar otra copia."), { type: "warning", sticky: true });
        }
        return false;
    },
});
