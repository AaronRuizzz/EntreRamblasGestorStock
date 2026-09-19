# -*- coding: utf-8 -*-
from odoo import _, api, models

from .mgs_permissions import require_manager

# move_type de account.move donde este partner es el CLIENTE (no un apunte
# donde aparece como proveedor en una factura de compra, que no cuenta como
# "venta" a efectos de este bloqueo).
_SALE_MOVE_TYPES = ("out_invoice", "out_refund", "out_receipt")


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._mgs_apply_default_payment_term()
        return partners

    def _mgs_apply_default_payment_term(self):
        """«Al contado» por defecto solo para particulares (decisión de la
        propietaria: a empresas se les deja elegir plazo). Se aplica al
        crear, sin pisar nunca una forma de pago ya elegida — ni aquí ni si
        se cambia is_company más tarde: un alta rápida desde el TPV crea la
        ficha con is_company=False sin que nadie la haya tocado."""
        immediate = self.env.ref("account.account_payment_term_immediate",
                                 raise_if_not_found=False)
        if not immediate:
            return
        for partner in self:
            if not partner.is_company and not partner.property_payment_term_id:
                partner.property_payment_term_id = immediate

    def mgs_pos_delete(self):
        """Botón "Eliminar cliente" del TPV (partner_line.xml).

        Solo la responsable de la tienda puede llamarlo. Si el cliente tiene
        alguna venta (TPV o factura) o algún encargo (mgs.event, que además
        bloquea el unlink a nivel de BD por su FK restrict), NO se borra: se
        archiva (active=False) y se avisa. Si no tiene nada de eso, se borra
        de verdad.
        """
        self.ensure_one()
        require_manager(self.env)
        if not self.exists():
            return {"result": "gone", "message": _("Ese cliente ya no existe.")}

        has_events = bool(self.env["mgs.event"].sudo().search_count(
            [("partner_id", "=", self.id)]))
        has_orders = bool(self.env["pos.order"].sudo().search_count(
            [("partner_id", "=", self.id)]))
        has_invoices = bool(self.env["account.move"].sudo().search_count(
            [("partner_id", "=", self.id), ("move_type", "in", _SALE_MOVE_TYPES)]))

        if has_events or has_orders or has_invoices:
            self.sudo().write({"active": False})
            return {
                "result": "archived",
                "message": _("«%s» tiene ventas o encargos: se ha archivado en vez "
                             "de eliminarse (deja de aparecer en las listas).",
                             self.name),
            }

        name = self.name
        try:
            self.sudo().unlink()
        except Exception:  # noqa: BLE001 - red de seguridad ante cualquier FK
            # que no hayamos previsto (otro módulo instalado, etc.): nunca
            # dejar una excepción cruda en la pantalla del TPV.
            self.sudo().write({"active": False})
            return {
                "result": "archived",
                "message": _("«%s» no se pudo eliminar del todo: se ha "
                             "archivado en su lugar.", name),
            }
        return {"result": "deleted", "message": _("«%s» eliminado.", name)}
