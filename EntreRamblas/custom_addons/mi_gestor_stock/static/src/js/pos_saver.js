/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { SaverScreen } from "@point_of_sale/app/screens/saver_screen/saver_screen";

// SaverScreen (el salvapantallas tras 5 min de inactividad, pos_store.js
// idleTimeout) no guardaba una referencia a la tienda: pos_saver.xml la
// necesita para pintar el logo de la compañía en vez del de Odoo.
patch(SaverScreen.prototype, {
    setup() {
        super.setup();
        this.pos = usePos();
    },
});
