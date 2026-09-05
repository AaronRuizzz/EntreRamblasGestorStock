/** @odoo-module **/
// Panel de inicio de Stock: avisos activos, productos a punto de caducar,
// los 3 productos con menos stock y el listado agrupado por categorías.
// Todos los datos vienen de product.template.mgs_dashboard_data() en una
// sola llamada (ver models/product_template.py).
import { registry } from "@web/core/registry";
import { useBus, useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class MgsStockDashboard extends Component {
    static template = "mi_gestor_stock.StockDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        // Escanear un producto aquí abre su ficha: sirve para consultar
        // precio y existencias con la pistola, sin teclear nada. Los dos
        // lectores son HID, así que el servicio "barcode" los recoge igual.
        const barcode = useService("barcode");
        useBus(barcode.bus, "barcode_scanned", (ev) =>
            this.onBarcodeScanned(ev.detail.barcode)
        );
        this.state = useState({
            loading: true,
            data: {
                alerts: [],
                expiring: [],
                low_stock: [],
                categories: [],
                currency: "€",
            },
            collapsed: {},
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("product.template", "mgs_dashboard_data", []);
        } finally {
            this.state.loading = false;
        }
    }

    get hasProducts() {
        return this.state.data.categories.length > 0;
    }

    isCollapsed(categId) {
        return !!this.state.collapsed[categId];
    }

    toggleCategory(categId) {
        this.state.collapsed[categId] = !this.state.collapsed[categId];
    }

    formatQty(qty) {
        return Number(qty).toLocaleString("es-ES", { maximumFractionDigits: 2 });
    }

    formatPrice(price) {
        return `${Number(price).toLocaleString("es-ES", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })} ${this.state.data.currency}`;
    }

    expiryLabel(days) {
        if (days < 0) {
            return `caducado hace ${Math.abs(days)} d.`;
        }
        if (days === 0) {
            return "caduca hoy";
        }
        return `caduca en ${days} d.`;
    }

    async onBarcodeScanned(barcode) {
        const found = await this.orm.call("product.template", "mgs_find_by_barcode", [barcode]);
        if (!found) {
            this.notification.add(
                `El código ${barcode} no está dado de alta. Añádelo desde Recepción.`,
                { type: "warning" }
            );
            return;
        }
        this.openProduct(found.id);
    }

    openProduct(productId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: productId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAlerts() {
        this.action.doAction("mi_gestor_stock.action_mgs_alerts");
    }

    openProducts() {
        this.action.doAction("mi_gestor_stock.action_mgs_products");
    }

    openReception() {
        this.action.doAction("mi_gestor_stock.action_mgs_reception");
    }

    async dismissNotice(noticeId) {
        await this.orm.call("mgs.stock.alert.notice", "action_mark_read", [[noticeId]]);
        await this.load();
    }
}

registry.category("actions").add("mgs_stock_dashboard", MgsStockDashboard);
