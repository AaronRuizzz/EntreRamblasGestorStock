/** @odoo-module **/
/**
 * Cobrar un encargo en caja.
 *
 * Desde el formulario del encargo, «Cobrar en caja» abre el TPV con
 * `?mgs_event=<id>`. Al arrancar, el TPV pide al servidor las partidas que se
 * venden (flores, ramos; el alquiler se queda en el encargo) y monta un pedido
 * con el cliente ya puesto. Al cobrarlo, la pantalla de pago avisa al servidor
 * (mgs_pos_link_order), que enlaza el pedido con el encargo
 * (`pos.order.mgs_event_ref`), marca esas partidas como entregadas —el stock lo
 * ha movido el propio TPV— y anota el cobro en el encargo (models/mgs_event.py,
 * _mgs_settle_event). Hay una segunda red en pos.order._process_order.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PosStore.prototype, {
    async afterProcessServerData() {
        await super.afterProcessServerData(...arguments);
        const params = new URLSearchParams(window.location.search);
        const eventId = parseInt(params.get("mgs_event"), 10);
        if (!Number.isInteger(eventId) || eventId <= 0) {
            return;
        }
        // Quita el parámetro: un refresco de página no debe recargar el encargo.
        let selectedLines;
        try {
            selectedLines = JSON.parse(params.get("mgs_lines") || "null");
        } catch {
            selectedLines = null;
        }
        params.delete("mgs_event");
        params.delete("mgs_lines");
        const query = params.toString();
        window.history.replaceState(
            {}, "", window.location.pathname + (query ? "?" + query : "")
        );
        try {
            const data = await this.data.call(
                "mgs.event", "mgs_pos_load_event", [eventId, selectedLines]
            );
            if (!data || data.error) {
                this.notification.add(
                    data?.error || _t("No se pudo cargar el encargo."),
                    { type: "warning" }
                );
                return;
            }
            await this._mgsLoadEventOrder(data);
        } catch {
            this.notification.add(
                _t("No se pudo cargar el encargo. Añade las partidas a mano."),
                { type: "danger" }
            );
        }
    },

    async _mgsLoadEventOrder(data) {
        let order = this.get_order();
        if (!order || order.lines.length) {
            order = this.add_new_order();
        }

        if (data.partner_id) {
            let partner = this.models["res.partner"].get(data.partner_id);
            if (!partner) {
                const loaded = await this.data.read("res.partner", [data.partner_id]);
                partner = loaded && loaded[0];
            }
            if (partner) {
                order.set_partner(partner);
            }
        }

        let missing = false;
        for (const line of data.lines) {
            const product = this.models["product.product"].get(line.product_id);
            if (!product) {
                missing = true;
                continue;
            }
            await this.addLineToCurrentOrder(
                {
                    product_id: product,
                    qty: line.qty,
                    price_unit: line.price_unit,
                    mgs_bouquet_spec: line.bouquet_spec || false,
                },
                {},
                false
            );
        }

        // El encargo del pedido se recuerda por uuid (lo usa la pantalla de pago
        // para avisar al servidor). Se marca también en el propio pedido por si
        // viaja al servidor al guardar (pos.order sincroniza todos sus campos):
        // entonces pos.order._process_order es una red más.
        (this._mgsEventByUuid ||= {})[order.uuid] = {
            eventId: data.event_id,
            lines: data.lines.map((line) => ({ line_id: line.event_line_id, qty: line.qty })),
        };

        if (missing) {
            this.notification.add(
                _t("Algún artículo del encargo no está disponible en el TPV; revísalo."),
                { type: "warning" }
            );
        }
        this.notification.add(
            _t("Encargo %s cargado. Revísalo y cóbralo.", data.name),
            { type: "info" }
        );
    },
});

patch(PaymentScreen.prototype, {
    async afterOrderValidation() {
        const order = this.currentOrder;
        const eventData = order && this.pos._mgsEventByUuid?.[order.uuid];
        const uuid = order?.uuid;
        const result = await super.afterOrderValidation(...arguments);
        if (eventData && uuid) {
            try {
                await this.pos.data.call("mgs.event", "mgs_pos_link_order", [eventData.eventId, uuid, eventData.lines]);
                delete this.pos._mgsEventByUuid[uuid];
            } catch {
                this.pos.notification.add(
                    _t("La venta se ha cobrado, pero el encargo no se ha marcado. Ábrelo y compruébalo."),
                    { type: "warning", sticky: true }
                );
            }
        }
        return result;
    },
});
