/** @odoo-module **/
// Página de inicio: lo primero que se ve al entrar. Deliberadamente sencilla —
// el emblema, el nombre de la tienda y un acceso claro a cada sección. Si hay
// avisos de stock pendientes lo indica, para que no queden enterrados.
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class MgsHome extends Component {
    static template = "mi_gestor_stock.Home";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ alerts: 0, products: 0, loaded: false, isManager: false, backupWarning: false, updateNotice: "" });
        onWillStart(async () => {
            try {
                const data = await this.orm.call("product.template", "mgs_home_summary", []);
                this.state.alerts = data.alerts;
                this.state.products = data.products;
                this.state.isManager = data.is_manager;
                this.state.backupWarning = data.backup_warning;
                this.state.updateNotice = data.update_notice;
            } finally {
                this.state.loaded = true;
            }
        });
    }

    open(xmlid) {
        this.action.doAction(xmlid);
    }
}

registry.category("actions").add("mgs_home", MgsHome);
