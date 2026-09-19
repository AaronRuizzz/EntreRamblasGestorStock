# -*- coding: utf-8 -*-
"""Factura completa (no el ticket) con el contenido que exige el art. 6 del
RD 1619/2012: NIF y domicilio del expedidor Y del destinatario, entre otras
cosas. El aspecto lo pone la plantilla nativa `account.report_invoice_document`
(NIF y dirección de la tienda ya salen solos, vía `web.external_layout`, si
están rellenos en la ficha de la compañía; el desglose de base/tipo/cuota de
IVA lo trae `account.document_tax_totals`), así que aquí solo se añaden dos
cosas que la plantilla nativa NO cubre:

  1. Nada impide hoy contabilizar una factura a un cliente sin NIF ni
     domicilio: `_mgs_check_legal_data` lo corta antes de confirmarla.
  2. Una rectificativa no señala en ningún sitio visible a qué factura
     rectifica (el campo `ref` lleva una referencia técnica en inglés
     traducido, «Reversión de: ...», que cumple la letra pero no se lee
     como tal) — ver report/mgs_account_invoice_report.xml.

Esto NO activa VERI*FACTU (huella encadenada, firma, QR tributario): sigue
siendo la decisión aplazada que documenta FACTURACION.md.
"""
from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _mgs_check_legal_data(self):
        for move in self:
            if move.move_type not in ("out_invoice", "out_refund"):
                continue
            missing = []
            company = move.company_id
            if not company.vat:
                missing.append(_(
                    "el NIF de la tienda (Configuración → Dispositivos → Datos de la tienda)"))
            if not (company.street or company.street2) or not company.city:
                missing.append(_(
                    "el domicilio de la tienda (Configuración → Dispositivos → Datos de la tienda)"))
            partner = move.commercial_partner_id
            if not partner:
                missing.append(_("un cliente identificado"))
            else:
                if not partner.vat:
                    missing.append(_("el NIF del cliente (%s)", partner.display_name))
                if not (partner.street or partner.street2) or not partner.city:
                    missing.append(_("el domicilio del cliente (%s)", partner.display_name))
            if missing:
                raise UserError(_(
                    "Esta factura no se puede confirmar: falta %s.\n\n"
                    "A diferencia del ticket, una factura completa tiene que llevar "
                    "el NIF y el domicilio de la tienda y del cliente (RD 1619/2012, "
                    "art. 6).", ", ".join(missing)))

    def action_post(self):
        self._mgs_check_legal_data()
        return super().action_post()

    def action_mgs_invoice_pdf(self):
        """PDF de la factura, generado al vuelo y guardado en la carpeta
        Facturas (mgs.config._mgs_save_output). No depende de que el adjunto
        legal de la factura ya exista, a diferencia de
        action_invoice_download_pdf / /account/download_invoice_documents:
        ese camino es el que fallaba al cobrar con factura desde el TPV
        cuando el adjunto aún no se había generado (ver
        static/src/js/pos_invoice.js, que sustituye la descarga nativa por
        este método solo dentro del TPV)."""
        self.ensure_one()
        self.check_access("read")
        pdf_content, report_type = self.env["ir.actions.report"]._render_qweb_pdf(
            "account.account_invoices", self.ids)
        if report_type != "pdf":
            raise UserError(_("No se ha podido generar el PDF de la factura."))
        filename = "%s.pdf" % (self.name or _("Factura")).replace("/", "-")
        config = self.env["mgs.config"]._mgs_get()
        config._mgs_save_output("facturas", filename, pdf_content)
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "raw": pdf_content,
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "download",
        }
