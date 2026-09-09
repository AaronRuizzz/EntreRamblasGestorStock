/** @odoo-module **/
/**
 * Montar un ramo en el mostrador.
 *
 * Al tocar un producto marcado como composición (models/mgs_bouquet.py) no se
 * añade la línea directamente: se abre este diálogo para elegir qué flores y
 * material lleva. La línea que se crea es UNA sola —lo que ve el cliente en el
 * ticket— y arrastra el contenido en `mgs_bouquet_spec`; el servidor lo valida
 * y descuenta cada tallo de su partida.
 *
 * El precio sugerido se calcula sumando el PVP de lo que lleva, pero se puede
 * cambiar: en una floristería el ramo vale más que sus flores (montaje). Aquí
 * NO se usa ni se enseña el coste: la dependienta no tiene acceso a costes
 * (ver mgs_permissions.py y `_load_pos_data_fields`).
 */
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { reactive } from "@odoo/owl";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { makeAwaitable } from "@point_of_sale/app/store/make_awaitable_dialog";

export class BouquetPopup extends Component {
    static template = "mi_gestor_stock.BouquetPopup";
    static components = { Dialog };
    static props = {
        product: Object,
        products: Array,
        currency: { type: String, optional: true },
        getPayload: Function,
        close: Function,
    };

    setup() {
        this.state = useState({
            search: "",
            // { productId: {product, qty} } — el orden de inserción es el orden
            // en que la dependienta las va cogiendo, que es lo que espera ver.
            chosen: [],
            price: null,
        });
    }

    get candidates() {
        const words = this.state.search.trim().toLowerCase();
        const list = this.props.products.filter((product) => {
            if (!words) return true;
            const name = (product.display_name || "").toLowerCase();
            const code = (product.barcode || "") + " " + (product.default_code || "");
            return name.includes(words) || code.toLowerCase().includes(words);
        });
        return list.slice(0, 60);
    }

    get suggestedPrice() {
        return this.state.chosen.reduce(
            (total, item) => total + (item.product.lst_price || 0) * item.qty, 0);
    }

    get price() {
        return this.state.price === null ? this.suggestedPrice : this.state.price;
    }

    get isValid() {
        return this.state.chosen.length > 0 && this.state.chosen.every((item) => item.qty > 0);
    }

    add(product) {
        const found = this.state.chosen.find((item) => item.product.id === product.id);
        if (found) {
            found.qty += 1;
        } else {
            this.state.chosen.push({ product, qty: 1 });
        }
    }

    step(item, amount) {
        item.qty = Math.round((item.qty + amount) * 100) / 100;
        if (item.qty <= 0) this.remove(item);
    }

    setQty(item, event) {
        const value = parseFloat((event.target.value || "").replace(",", "."));
        item.qty = Number.isFinite(value) && value > 0 ? value : 0;
    }

    setPrice(event) {
        const value = parseFloat((event.target.value || "").replace(",", "."));
        this.state.price = Number.isFinite(value) && value >= 0 ? value : 0;
    }

    remove(item) {
        const index = this.state.chosen.indexOf(item);
        if (index >= 0) this.state.chosen.splice(index, 1);
    }

    confirm() {
        if (!this.isValid) return;
        this.props.getPayload({
            price: this.price,
            components: this.state.chosen.map((item) => ({
                product_id: item.product.id,
                qty: item.qty,
            })),
        });
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}

patch(ProductScreen.prototype, {
    async addProductToOrder(product) {
        if (!product.mgs_is_composition) {
            return super.addProductToOrder(...arguments);
        }
        // Solo material con existencias reales: un ramo no puede llevar dentro
        // otro ramo, ni servicios. El servidor rechaza lo demás igualmente.
        const products = this.pos.models["product.product"]
            .getAll()
            .filter((item) => item.is_storable && !item.mgs_is_composition && item.available_in_pos)
            .sort((a, b) => (a.display_name || "").localeCompare(b.display_name || ""));
        const payload = await makeAwaitable(this.dialog, BouquetPopup, {
            product,
            products,
            currency: this.pos.currency?.symbol || "",
        });
        if (!payload) return;
        await reactive(this.pos).addLineToCurrentOrder(
            {
                product_id: product,
                qty: 1,
                price_unit: payload.price,
                mgs_bouquet_spec: JSON.stringify(payload.components),
            },
            {}
        );
    },
});
