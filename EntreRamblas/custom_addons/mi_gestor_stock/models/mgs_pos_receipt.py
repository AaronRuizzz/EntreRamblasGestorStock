# -*- coding: utf-8 -*-
"""Datos que necesita el informe PDF del ticket (report/pos_order_receipt_report.xml).

El ticket ESC/POS (mgs_config.py:_mgs_pos_ticket) y este informe muestran el
mismo contenido por dos caminos distintos (bytes de impresora térmica vs.
QWeb/PDF), así que el desglose de IVA y el relabel del cambio se repiten
aquí: son ~10 líneas cada uno, no compensa acoplar un modelo (pos.order) con
el otro (mgs.config) por evitar duplicarlas.
"""
from uuid import uuid4

from odoo import _, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_mgs_reprint_ticket(self):
        """Botón «Reimprimir en la térmica» de Informes → Tickets.

        Reutiliza el mismo camino que el TPV (mgs_pos_print_order, con outbox
        transaccional: mgs_hardware_job.py): una petición desde el backend no
        es distinta de una del TPV salvo en quién la pide. Se manda siempre
        con `reprint_key` propio (no el «auto» del cobro) para que quede
        registrada como una reimpresión, no como el ticket original.
        """
        self.ensure_one()
        job = self.env["mgs.config"].mgs_pos_print_order(self.id, reprint_key=str(uuid4()))
        if job.get("state") == "disabled":
            return self.env["mgs.config"]._mgs_notify(
                _("No hay impresora configurada (Configuración → Dispositivos)."), "warning")
        return self.env["mgs.config"]._mgs_notify(
            _("Reimpresión solicitada. Comprueba la impresora."))

    def _mgs_receipt_date_str(self):
        """Misma fecha/hora, mismo formato, que _mgs_pos_ticket."""
        self.ensure_one()
        return fields.Datetime.context_timestamp(
            self, self.date_order).strftime("%d/%m/%Y %H:%M")

    def _mgs_receipt_qr(self, data):
        """PNG en base64 de un QR con `data`, o False si `data` está vacío.

        Un PDF no tiene el comando QR nativo que sí usa la impresora térmica
        (mgs_escpos.py:qr()): aquí hace falta generar la imagen de verdad.
        Delegado en mgs.config para no repetir la dependencia de `qrcode` en
        los tres sitios que necesitan esta misma imagen (este informe, el
        recibo en pantalla del TPV y, de rebote, mgs_pos_hardware_info)."""
        self.ensure_one()
        return self.env["mgs.config"]._mgs_qr_png(data)

    def _mgs_receipt_review_url(self):
        """URL de la reseña de Google (mgs.config.google_review_url), o
        False si no está rellena. Separado de _mgs_receipt_review_qr() para
        que el ticket ESC/POS (mgs_config.py:_mgs_pos_ticket) pueda pasarle
        el dato en crudo a doc.qr() en vez de una imagen PNG."""
        self.ensure_one()
        config = self.env["mgs.config"].sudo()._mgs_get()
        return (config.google_review_url or "").strip() or False

    def _mgs_receipt_review_qr(self):
        """QR a la reseña de Google, como imagen PNG (para el PDF)."""
        self.ensure_one()
        return self._mgs_receipt_qr(self._mgs_receipt_review_url())

    def _mgs_receipt_website_url(self):
        """URL completa de la web de la tienda, o False si no está
        configurada. El campo "website" vive en res.partner (no en
        res.company: esta instalación no depende del módulo "website", que
        es quien añadiría un campo propio a la compañía), así que se lee de
        company.partner_id. Antepone https:// si se escribió como
        "clavelyazahar.es" en vez de una URL completa."""
        self.ensure_one()
        website = (self.company_id.partner_id.website or "").strip()
        if not website:
            return False
        if not website.startswith(("http://", "https://")):
            website = "https://" + website
        return website

    def _mgs_receipt_website_qr(self):
        """QR a la web de la tienda."""
        self.ensure_one()
        return self._mgs_receipt_qr(self._mgs_receipt_website_url())

    def _mgs_receipt_invoice_portal_url(self):
        """URL del formulario donde la clienta puede pedir la factura de
        esta venta por su cuenta: el mismo destino que ya usa el recibo de
        pantalla del TPV (point_of_sale/static/src/app/models/pos_order.js,
        campo `pos_qr_code`), no algo propio de este módulo."""
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        return base_url.rstrip("/") + "/pos/ticket/"

    def _mgs_receipt_invoice_qr_ready(self):
        """Mismas condiciones que en pantalla: el ajuste de la compañía
        activado, la venta ya cobrada (no un ticket en curso) y con su
        código único puesto — lo genera el TPV al crear la venta
        (`ticket_code: random5Chars()` en pos_store.js); una venta fabricada
        a mano, como en un test, puede no tenerlo."""
        self.ensure_one()
        return bool(
            self.company_id.point_of_sale_use_ticket_qr_code
            and self.state != "draft"
            and self.ticket_code
        )

    def _mgs_receipt_invoice_qr(self):
        """QR para pedir la factura de esta venta online, en el ticket PDF.

        Es el mismo QR que el recibo de pantalla del TPV (`pos_qr_code`)
        enseña cuando ese recibo se imprime por el navegador — bien porque
        se pulsa «Imprimir factura», bien porque Configuración →
        Dispositivos → «Imprimir el ticket del TPV automáticamente» está
        desactivado. Reimprimir la venta como PDF desde el backend se
        quedaba sin él aunque el papel sí lo llevara."""
        self.ensure_one()
        if not self._mgs_receipt_invoice_qr_ready():
            return False
        if self.company_id.point_of_sale_ticket_portal_url_display_mode not in (
                "qr_code", "qr_code_and_url"):
            return False
        return self._mgs_receipt_qr(self._mgs_receipt_invoice_portal_url())

    def _mgs_receipt_invoice_url_text(self):
        """Enlace en texto, solo cuando el ajuste de la compañía pide
        enseñarlo (además del QR, o en vez de él)."""
        self.ensure_one()
        if not self._mgs_receipt_invoice_qr_ready():
            return False
        if self.company_id.point_of_sale_ticket_portal_url_display_mode not in (
                "url", "qr_code_and_url"):
            return False
        return self._mgs_receipt_invoice_portal_url()

    def _mgs_receipt_tax_breakdown(self):
        """Agrupado por TIPO impositivo (no por línea ni por el nombre interno
        del impuesto de l10n_es) — mismo criterio que _mgs_pos_ticket."""
        self.ensure_one()
        taxes = {}
        for line in self.lines:
            label = ", ".join(
                _("IVA %g%%", tax.amount) if tax.amount_type == "percent" else tax.name
                for tax in line.tax_ids) or _("Sin IVA")
            base, quota = taxes.get(label, (0.0, 0.0))
            taxes[label] = (base + line.price_subtotal,
                            quota + line.price_subtotal_incl - line.price_subtotal)
        return [{"label": label, "base": base, "quota": quota}
                for label, (base, quota) in taxes.items()]

    def _mgs_receipt_payments(self):
        """Cada línea de pago, con el cambio (importe negativo) relabelado."""
        self.ensure_one()
        result = []
        for payment in self.payment_ids:
            label = payment.payment_method_id.name
            amount = payment.amount
            if amount < 0:
                label, amount = _("Cambio"), -amount
            result.append({"label": label, "amount": amount})
        return result
