# -*- coding: utf-8 -*-
"""Datos que necesita el informe PDF del ticket (report/pos_order_receipt_report.xml).

El ticket ESC/POS (mgs_config.py:_mgs_pos_ticket) y este informe muestran el
mismo contenido por dos caminos distintos (bytes de impresora térmica vs.
QWeb/PDF), así que el desglose de IVA y el relabel del cambio se repiten
aquí: son ~10 líneas cada uno, no compensa acoplar un modelo (pos.order) con
el otro (mgs.config) por evitar duplicarlas.
"""
import base64
import io

import qrcode

from odoo import _, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _mgs_receipt_date_str(self):
        """Misma fecha/hora, mismo formato, que _mgs_pos_ticket."""
        self.ensure_one()
        return fields.Datetime.context_timestamp(
            self, self.date_order).strftime("%d/%m/%Y %H:%M")

    def _mgs_receipt_qr(self, data):
        """PNG en base64 de un QR con `data`, o False si `data` está vacío.

        Un PDF no tiene el comando QR nativo que sí usa la impresora térmica
        (mgs_escpos.py:qr()): aquí hace falta generar la imagen de verdad.
        """
        self.ensure_one()
        data = (data or "").strip()
        if not data:
            return False
        buffer = io.BytesIO()
        qrcode.make(data, box_size=4, border=1).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def _mgs_receipt_review_qr(self):
        """QR a la reseña de Google (mgs.config.google_review_url)."""
        self.ensure_one()
        config = self.env["mgs.config"].sudo()._mgs_get()
        return self._mgs_receipt_qr(config.google_review_url)

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
