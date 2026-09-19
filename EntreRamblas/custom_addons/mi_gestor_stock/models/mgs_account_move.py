# -*- coding: utf-8 -*-
"""Factura completa (no el ticket) con el contenido que exige el art. 6 del
RD 1619/2012: NIF y domicilio del expedidor Y del destinatario, entre otras
cosas. El aspecto lo pone la plantilla nativa `account.report_invoice_document`
(NIF y dirección de la tienda ya salen solos, vía `web.external_layout`, si
están rellenos en la ficha de la compañía; el desglose de base/tipo/cuota de
IVA lo trae `account.document_tax_totals`), así que aquí solo se añaden dos
cosas que la plantilla nativa NO cubre:

  1. Nada impide contabilizar una factura a un cliente sin NIF, domicilio
     completo, razón social de la tienda o plazo de pago:
     `_mgs_check_legal_data` lo corta antes de confirmarla. Se comprueba en
     `_post()`, no en `action_post()`: el TPV factura llamando directamente
     a `_post()` (point_of_sale/models/pos_order.py,
     `_generate_pos_order_invoice`), así que comprobarlo solo en
     `action_post()` dejaba colar desde caja facturas sin estos datos.
     Cubre `out_invoice`/`out_refund`/`out_receipt`; el plazo de pago solo
     se exige en factura/rectificativa, no en el recibo simplificado.
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

    # move_type donde el cliente recibe el documento (no un apunte donde el
    # partner es proveedor). out_receipt (factura simplificada/ticket con
    # datos de cliente) lleva las mismas exigencias que out_invoice: si se
    # le pone un cliente identificado, el art. 6 aplica igual.
    _MGS_LEGAL_MOVE_TYPES = ("out_invoice", "out_refund", "out_receipt")

    def _mgs_check_legal_data(self):
        for move in self:
            if move.move_type not in self._MGS_LEGAL_MOVE_TYPES:
                continue
            missing = []
            company = move.company_id
            if not company.name:
                missing.append(_(
                    "la razón social de la tienda (Configuración → Dispositivos → Datos de la tienda)"))
            if not company.vat:
                missing.append(_(
                    "el NIF de la tienda (Configuración → Dispositivos → Datos de la tienda)"))
            if not (company.street or company.street2) or not company.city or not company.zip \
                    or not company.country_id:
                missing.append(_(
                    "el domicilio completo de la tienda —calle, código postal, ciudad y país— "
                    "(Configuración → Dispositivos → Datos de la tienda)"))
            partner = move.commercial_partner_id
            if not partner:
                missing.append(_("un cliente identificado"))
            else:
                if not partner.vat:
                    missing.append(_("el NIF del cliente (%s)", partner.display_name))
                if not (partner.street or partner.street2) or not partner.city or not partner.zip \
                        or not partner.country_id:
                    missing.append(_(
                        "el domicilio completo del cliente —calle, código postal, ciudad y "
                        "país— (%s)", partner.display_name))
            if move.move_type in ("out_invoice", "out_refund") and not move.invoice_payment_term_id:
                missing.append(_("el plazo de pago"))
            if missing:
                raise UserError(_(
                    "Esta factura no se puede confirmar: falta %s.\n\n"
                    "A diferencia del ticket, una factura completa tiene que llevar "
                    "el NIF y el domicilio de la tienda y del cliente (RD 1619/2012, "
                    "art. 6).", ", ".join(missing)))

    def _post(self, soft=True):
        # Se comprueba aquí, no en action_post(): action_post() sí llama a
        # _post() (account_move.py), pero el TPV factura directamente contra
        # _post() (point_of_sale/models/pos_order.py,
        # _generate_pos_order_invoice) sin pasar por action_post(), así que
        # comprobarlo solo ahí dejaba colar facturas sin NIF ni domicilio
        # cobradas en caja — el hueco legal más serio que había.
        self._mgs_check_legal_data()
        return super()._post(soft=soft)

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


class AccountEdiCii(models.AbstractModel):
    """Item 5 del parte de la tienda: pagar con "factura" en Vender lanzaba
    un error de Odoo con un parámetro "como date_started / deferred" —
    reproducido en tests/test_invoice.py (TestInvoiceFromPos): es
    `deferred_start_date`, tal cual.

    `account.move._generate_and_send()`, que el TPV llama SIEMPRE al
    facturar (point_of_sale/models/pos_order.py), incrusta de forma
    incondicional un Factur-X en el PDF («Always silently generate a
    Factur-X... for inter-portability», account_edi_ubl_cii/models/
    account_move_send.py) — no es opcional ni depende de ningún ajuste de
    formato de factura electrónica de la empresa. Para construirlo,
    `_cii_get_billing_specified_period_node` (account_edi_ubl_cii/models/
    account_edi_cii.py) lee `move_line.deferred_start_date` /
    `.deferred_end_date` SIN comprobar antes si el campo existe —al
    contrario que otro punto del mismo módulo un poco más abajo
    (account_edi_xml_cii_facturx.py, que sí hace
    `line._fields.get('deferred_start_date')`)—. Esos dos campos son de la
    gestión de periodificación de Enterprise (`account_accountant`), que
    esta instalación no tiene, así que cualquier factura con IVA
    (out_invoice) reventaba `AttributeError` en cuanto el TPV intentaba
    generar el PDF, después de cobrar y de mover el stock: la venta ya
    estaba hecha, pero la factura no salía y la dependienta veía un error
    de Odoo en plena caja.

    Mismo cálculo que el original, con la comprobación que le falta.
    `account_edi_ubl_cii` se declara como dependencia explícita en
    __manifest__.py porque aquí se hereda uno de sus modelos (aunque ya
    llega solo, instalado por `l10n_es` -> `l10n_es_edi_facturae` ->
    `account_edi_ubl_cii`, auto_install)."""
    _inherit = "account.edi.cii"

    def _cii_get_billing_specified_period_node(self, vals):
        invoice = vals["invoice"]
        has_deferred = "deferred_start_date" in self.env["account.move.line"]._fields
        billing_start_dates = [invoice.invoice_date] if invoice.invoice_date else []
        billing_end_dates = [invoice.invoice_date_due] if invoice.invoice_date_due else []
        if has_deferred:
            billing_start_dates += [line.deferred_start_date for line in invoice.invoice_line_ids
                                    if line.deferred_start_date]
            billing_end_dates += [line.deferred_end_date for line in invoice.invoice_line_ids
                                  if line.deferred_end_date]
        start_date = min(billing_start_dates) if billing_start_dates else None
        end_date = max(billing_end_dates) if billing_end_dates else None
        return {
            "ram:StartDateTime": self._cii_get_date_time_string_node(vals, start_date) if start_date else None,
            "ram:EndDateTime": self._cii_get_date_time_string_node(vals, end_date) if end_date else None,
        }
