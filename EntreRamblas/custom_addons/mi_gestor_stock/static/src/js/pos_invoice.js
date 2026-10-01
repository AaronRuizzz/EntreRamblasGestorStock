/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { AccountMoveService } from "@account/services/account_move_service";

// El botón «Imprimir factura» del TPV (y «¿Necesita factura?» al cobrar)
// pasan por aquí. El método nativo (action_invoice_download_pdf ->
// /account/download_invoice_documents/.../pdf) exige que el adjunto legal de
// la factura ya exista; si el envío por correo o el cron que lo genera no ha
// corrido todavía, la descarga falla con un error de servidor en vez de un
// PDF. Aquí se sustituye por mgs_account_move.action_mgs_invoice_pdf(), que
// renderiza el informe (report/mgs_account_invoice_report.xml) al vuelo y lo
// guarda en la carpeta Facturas (mgs_output.py).
//
// SOLO se guarda en la carpeta Facturas: no se lanza la acción de descarga que
// devuelve el servidor (abría el PDF en el navegador/Edge) ni se muestra
// notificación alguna. Antes, `this.notification` no existe en este servicio
// y `_t` no estaba importado: tras guardar bien la factura saltaba el error
// «Cannot read properties of undefined (reading 'add')».
//
// Solo se toca en el bundle del TPV (point_of_sale._assets_pos): la
// descarga de facturas del backend (lista/ficha de account.move) sigue el
// camino nativo, donde el adjunto sí se genera en el flujo normal de
// contabilidad.
patch(AccountMoveService.prototype, {
    async downloadPdf(accountMoveId) {
        await this.orm.call("account.move", "action_mgs_invoice_pdf", [accountMoveId]);
    },
});
