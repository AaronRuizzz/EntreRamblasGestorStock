/** @odoo-module **/
/**
 * Regresión: la pantalla de recibo (point_of_sale.ReceiptScreen) se quedaba
 * en blanco al completar una venta después de recortar el bloque de email/
 * SMS con un t-inherit por XPath (ver pos.scss: ahora se oculta por CSS sin
 * tocar la plantilla). Este tour completa dos ventas reales en el navegador
 * — único modo de detectar este tipo de fallo de render, que un chequeo
 * estático de XPath (como el de test_pos_receipt.py) no ve.
 */
import * as ProductScreen from "@point_of_sale/../tests/tours/utils/product_screen_util";
import * as PaymentScreen from "@point_of_sale/../tests/tours/utils/payment_screen_util";
import * as ReceiptScreen from "@point_of_sale/../tests/tours/utils/receipt_screen_util";
import * as Dialog from "@point_of_sale/../tests/tours/utils/dialog_util";
import * as Chrome from "@point_of_sale/../tests/tours/utils/chrome_util";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("mgs_receipt_screen_after_payment", {
    steps: () =>
        [
            // La sesión ya existe en servidor (abierta con open_ui() antes
            // de arrancar el tour). El navegador aún pasa por dos pantallas
            // antes del TPV: la screen-login (Chrome.startPoS()) y, como
            // cash_control está activo (hay un método de pago en efectivo),
            // el modal "Control de apertura" — interfaz en español (es_ES).
            Chrome.startPoS(),
            Dialog.confirm("Abrir caja registradora"),

            // Pulsar el mismo producto dos veces: debe agrupar en una sola
            // línea con cantidad 2 (regresión: pos_hardware.js isLotTracked
            // — Odoo bloquea el merge nativo para productos con lote, y
            // aquí todo el catálogo lo usa para la caducidad).
            ProductScreen.clickDisplayedProduct("Rosa TPV"),
            ProductScreen.clickDisplayedProduct("Rosa TPV"),
            {
                content: "las dos pulsaciones se agrupan en una sola línea",
                trigger: ".order-container .orderline",
                run: () => {
                    const lines = document.querySelectorAll(".order-container .orderline");
                    if (lines.length !== 1) {
                        throw new Error(`Se esperaba 1 línea agrupada, hay ${lines.length}.`);
                    }
                },
            },

            // Venta en efectivo -----------------------------------------
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Cash"),
            PaymentScreen.clickValidate(),
            ReceiptScreen.receiptIsThere(),
            {
                // El input sigue en el DOM a propósito (se oculta por CSS,
                // no se recorta la plantilla — ver pos.scss): hay que
                // comprobar que no es VISIBLE, no que no exista.
                content: "no debe verse el envío del ticket por email/SMS",
                trigger: ".receipt-screen .pos-receipt",
                run: () => {
                    const input = document.querySelector(".receipt-screen .send-receipt-email-input");
                    if (input && input.offsetParent !== null) {
                        throw new Error("El bloque de email/SMS sigue visible en el recibo.");
                    }
                },
            },
            {
                content: "el botón de imprimir sigue disponible",
                trigger: ".receipt-screen .button.print",
            },
            ReceiptScreen.clickNextOrder(),
            ProductScreen.isShown(),

            // Venta con tarjeta: pasa por la confirmación de datáfono
            // propia de la tienda (pos_validation.js) antes del recibo.
            ProductScreen.clickDisplayedProduct("Rosa TPV"),
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            Dialog.confirm("Pago aceptado"),
            ReceiptScreen.receiptIsThere(),
            ReceiptScreen.clickNextOrder(),
            ProductScreen.isShown(),
        ].flat(),
});
