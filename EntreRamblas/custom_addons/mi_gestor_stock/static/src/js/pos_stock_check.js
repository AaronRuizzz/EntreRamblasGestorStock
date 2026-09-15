/** @odoo-module **/
/**
 * Venta con falta de stock.
 *
 * Antes de aceptar una falta de existencias, la dependienta ve el producto,
 * lo que queda y lo que se pide, y decide: "Cancelar" o "Añadir de todos
 * modos". Aceptar registra la autorización en el servidor
 * (`mgs_authorize_deficit`, models/mgs_pos_stock.py) contra ESTA venta y ESE
 * producto: si la cantidad sube después, se vuelve a preguntar.
 *
 * `mgsResolveDeficits` es el único punto de entrada que usan `pos_validation.js`
 * (al añadir/escanear, al cambiar de línea y al cobrar/validar) — así el
 * diálogo y el registro de la autorización se hacen siempre igual.
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ask } from "@point_of_sale/app/store/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

function mgsLinesPayload(order) {
    return order.lines.map((line) => {
        const payload = { product_id: line.product_id.id, qty: line.qty };
        if (line.mgs_bouquet_spec) {
            payload.bouquet_spec = line.mgs_bouquet_spec;
        }
        return payload;
    });
}

// Un déficit de un componente de ramo no aparece en ninguna línea con ese
// product_id (el ramo es una sola línea con `mgs_bouquet_spec`): hay que
// mirar dentro del contenido del ramo para saber qué línea marcar.
function mgsLinesForDeficit(order, productId) {
    return order.lines.filter((line) => {
        if (line.product_id.id === productId) {
            return true;
        }
        if (!line.mgs_bouquet_spec) {
            return false;
        }
        try {
            const components = JSON.parse(line.mgs_bouquet_spec);
            return components.some((item) => item.product_id === productId);
        } catch {
            return false;
        }
    });
}

patch(PosStore.prototype, {
    async mgsCheckStock(order = this.get_order(), lines = null) {
        return rpc("/web/dataset/call_kw/pos.order/mgs_check_stock", {
            model: "pos.order", method: "mgs_check_stock",
            args: [this.session.id, lines || mgsLinesPayload(order), order.uuid],
            kwargs: {},
        });
    },

    async mgsAuthorizeDeficit(order, lines = null) {
        return rpc("/web/dataset/call_kw/pos.order/mgs_authorize_deficit", {
            model: "pos.order", method: "mgs_authorize_deficit",
            args: [this.session.id, order.uuid, lines || mgsLinesPayload(order)],
            kwargs: {},
        });
    },

    // Comprueba, pregunta y autoriza si hace falta. Devuelve el último
    // resultado de mgs_check_stock/mgs_authorize_deficit — con "ok" a true
    // solo cuando no queda ninguna falta sin resolver — o
    // {ok: false, cancelled: true} si la dependienta ha cancelado, o
    // {ok: false, networkError: true} si el servidor local no responde.
    async mgsResolveDeficits(order, lines = null) {
        let result;
        try {
            result = await this.mgsCheckStock(order, lines);
        } catch {
            this.dialog.add(AlertDialog, {
                title: _t("No se puede comprobar el stock"),
                body: _t("El servidor local no responde ahora mismo. Tu venta se mantiene "
                        + "tal y como está: vuelve a intentarlo en un momento."),
            });
            return { ok: false, networkError: true };
        }
        if (result.ok || result.already_confirmed) {
            return result;
        }
        const pendingProductIds = result.deficits.map((deficit) => deficit.product_id);
        for (const deficit of result.deficits) {
            const accepted = await ask(this.dialog, {
                title: _t("No hay existencias suficientes"),
                body: _t(
                    "%(product)s: quedan %(available)s y se están pidiendo %(requested)s.\n¿Añadir el producto de todos modos?",
                    { product: deficit.product_name, available: deficit.available, requested: deficit.requested }
                ),
                confirmLabel: _t("Añadir de todos modos"),
                cancelLabel: _t("Cancelar"),
            });
            if (!accepted) {
                return { ok: false, cancelled: true };
            }
        }
        try {
            result = await this.mgsAuthorizeDeficit(order, lines);
        } catch {
            this.dialog.add(AlertDialog, {
                title: _t("No se puede confirmar la venta con falta de stock"),
                body: _t("El servidor local no ha respondido al autorizarlo. Tu venta se "
                        + "mantiene tal y como está: vuelve a intentarlo."),
            });
            return { ok: false, networkError: true };
        }
        // Aviso persistente en el pedido y marca en cada línea afectada
        // (incluidos los componentes de un ramo, buscando en qué línea
        // aparece cada producto que se acaba de autorizar a faltar).
        order.uiState.mgsStockException = true;
        for (const productId of pendingProductIds) {
            for (const line of mgsLinesForDeficit(order, productId)) {
                line.uiState.mgsStockException = true;
            }
        }
        return result;
    },
});

patch(ProductScreen.prototype, {
    async addProductToOrder(product) {
        await super.addProductToOrder(...arguments);
        await this.pos.mgsResolveDeficits(this.pos.get_order());
    },
});

patch(OrderSummary.prototype, {
    clickLine(ev, orderline) {
        const previous = this.currentOrder.get_selected_orderline();
        super.clickLine(ev, orderline);
        if (previous && previous !== this.currentOrder.get_selected_orderline()) {
            this.pos.mgsResolveDeficits(this.currentOrder);
        }
    },
});
