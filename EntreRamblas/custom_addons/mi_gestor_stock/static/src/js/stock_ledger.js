/** @odoo-module **/
// Entradas y salidas: filtros Todo/Entradas/Salidas, producto y fechas
// (por defecto el mes actual). Los datos vienen ya formados de
// mgs.stock.ledger.mgs_ledger_data() (ver models/mgs_stock_ledger.py) —
// aquí solo se pintan y se relanza la consulta al cambiar un filtro.
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class MgsStockLedger extends Component {
    static template = "mi_gestor_stock.StockLedger";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            direction: "all",
            productQuery: "",
            dateFrom: "",
            dateTo: "",
            data: { rows: [], can_see_cost: false, truncated: false, date_from: "", date_to: "" },
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("mgs.stock.ledger", "mgs_ledger_data", [], {
                direction: this.state.direction === "all" ? null : this.state.direction,
                product_query: this.state.productQuery || null,
                date_from: this.state.dateFrom || null,
                date_to: this.state.dateTo || null,
            });
            // El servidor decide el rango por defecto (mes actual, zona
            // Madrid); se refleja en los campos de fecha para que se vea
            // cuál es y se pueda cambiar desde ahí.
            this.state.dateFrom = this.state.data.date_from;
            this.state.dateTo = this.state.data.date_to;
        } finally {
            this.state.loading = false;
        }
    }

    setDirection(direction) {
        this.state.direction = direction;
        this.load();
    }

    onProductInput(ev) {
        this.state.productQuery = ev.target.value;
    }

    onDateFromChange(ev) {
        this.state.dateFrom = ev.target.value;
        this.load();
    }

    onDateToChange(ev) {
        this.state.dateTo = ev.target.value;
        this.load();
    }

    onProductSearch() {
        this.load();
    }

    formatQty(qty) {
        return Number(qty).toLocaleString("es-ES", { maximumFractionDigits: 2 });
    }

    formatCost(cost) {
        return Number(cost).toLocaleString("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
}

registry.category("actions").add("mgs_stock_ledger", MgsStockLedger);
