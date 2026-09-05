/** @odoo-module **/
// Puente entre el TPV y el hardware de la tienda, SIN IoT Box.
//
// Odoo Community da por hecho que el cajón y la impresora térmica cuelgan de
// una IoT Box (o de una Epson ePOS). Aquí no hay ninguna de las dos: la
// impresora Approx está en la misma red (o en el mismo PC) que el servidor,
// así que el servidor le habla ESC/POS directamente (models/mgs_config.py) y
// el TPV solo tiene que avisar en dos momentos:
//
//   1. cuando toca abrir el cajón  -> openCashbox()
//   2. cuando toca imprimir ticket -> printReceipt()
//
// Todo va envuelto en try/catch y con vuelta atrás al comportamiento estándar:
// un fallo de la impresora NUNCA puede dejar una venta a medias.
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/network/rpc";
import { HardwareProxy } from "@point_of_sale/app/hardware_proxy/hardware_proxy_service";
import { PosStore } from "@point_of_sale/app/store/pos_store";

async function mgsCall(method, args = []) {
    return rpc(
        `/web/dataset/call_kw/mgs.config/${method}`,
        { model: "mgs.config", method, args, kwargs: {} },
        { silent: true }
    );
}

patch(HardwareProxy.prototype, {
    /**
     * El TPV ya llama aquí solo: al cobrar en efectivo o cuando hay cambio
     * que devolver (payment_screen.js -> _finalizeValidation), y desde los
     * diálogos de apertura y cierre de caja. Se mantiene la llamada original
     * (por si algún día hay IoT Box) y se añade la nuestra.
     */
    async openCashbox(action = false) {
        const result = await super.openCashbox(action);
        try {
            if (this.mgsDrawer !== false) {
                await mgsCall("mgs_pos_open_drawer");
            }
        } catch (error) {
            console.warn("mi_gestor_stock: no se pudo abrir el cajón", error);
        }
        return result;
    },
});

patch(PosStore.prototype, {
    async processServerData() {
        const result = await super.processServerData(...arguments);
        // Una sola consulta al abrir el TPV: así imprimir un ticket no gasta
        // una llamada extra al servidor para preguntar si hay impresora.
        this.mgsHardware = { escpos_receipt: false, drawer: false };
        try {
            this.mgsHardware = await mgsCall("mgs_pos_hardware_info");
            this.hardwareProxy.mgsDrawer = this.mgsHardware.drawer;
        } catch (error) {
            console.warn("mi_gestor_stock: hardware no disponible", error);
        }
        return result;
    },

    /**
     * Ticket directo por la térmica, sin el diálogo de impresión del
     * navegador. Si el pedido todavía no está en el servidor o la impresora
     * no responde, se cae al comportamiento normal de Odoo (imprimir por el
     * navegador), de modo que el cliente siempre se lleva su ticket.
     */
    async printReceipt(options = {}) {
        const order = options.order || this.get_order();
        if (this.mgsHardware?.escpos_receipt && typeof order?.id === "number") {
            try {
                const printed = await mgsCall("mgs_pos_print_order", [order.id]);
                if (printed) {
                    if (!options.printBillActionTriggered) {
                        order.nb_print += 1;
                        await this.data.write("pos.order", [order.id], {
                            nb_print: order.nb_print,
                        });
                    }
                    return true;
                }
            } catch (error) {
                console.warn("mi_gestor_stock: fallo al imprimir el ticket", error);
            }
        }
        return super.printReceipt(options);
    },
});
