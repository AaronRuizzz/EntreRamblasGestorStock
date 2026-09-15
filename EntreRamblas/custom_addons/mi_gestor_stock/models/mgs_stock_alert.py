# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class MgsStockAlert(models.Model):
    """Aviso configurable sobre el stock de un producto.

    Dos sabores (campo `alert_type`):
      - 'threshold': salta cuando quedan <= `min_qty` unidades. Se evalua EN VIVO
        (no depende del cron), asi que aparece y desaparece solo segun el stock.
      - 'periodic' : cada X dias / semanal / mensual deja un aviso informativo con
        el stock que hay en ese momento. Lo genera el cron y se descarta a mano.
    """
    _name = "mgs.stock.alert"
    _description = "Aviso de stock"
    _order = "product_id, id"

    product_id = fields.Many2one(
        "product.template", string="Producto", required=True, ondelete="cascade",
        domain=[("is_storable", "=", True)])
    alert_type = fields.Selection([
        ("threshold", "Cuando baje de una cantidad"),
        ("periodic", "Resumen cada cierto tiempo"),
    ], string="Tipo de aviso", default="threshold", required=True)

    # --- threshold ---
    min_qty = fields.Float(
        "Avisar cuando queden", default=10.0, digits="Product Unit of Measure",
             help="Salta el aviso cuando el stock sea igual o menor que esta cantidad.")

    # --- periodic ---
    interval_type = fields.Selection([
        ("days", "Cada X días"),
        ("weekly", "Semanal"),
        ("monthly", "Mensual"),
    ], string="Frecuencia", default="weekly")
    interval_number = fields.Integer("Cada (días)", default=7)

    active = fields.Boolean("Activo", default=True)
    last_run = fields.Datetime("Último aviso enviado", readonly=True)

    qty_available = fields.Float(
        related="product_id.qty_available", string="Stock actual", readonly=True)
    is_triggered = fields.Boolean(
        "Saltando ahora", compute="_compute_is_triggered",
        help="Solo para los avisos por cantidad: indica si el stock está en el límite.")

    # Nombre libre y opcional: "Rosas San Valentín". Si se deja vacío se usa el
    # texto automático (auto_label) tanto en la lista como en el panel.
    name = fields.Char(
        "Nombre del aviso",
        help="Opcional. Si lo dejas en blanco, el aviso se nombra solo a partir "
             "del producto y las condiciones.")
    auto_label = fields.Char(compute="_compute_auto_label")

    @api.depends("product_id", "alert_type", "min_qty", "interval_type", "interval_number")
    def _compute_auto_label(self):
        for alert in self:
            product = alert.product_id.name or _("(sin producto)")
            if alert.alert_type == "threshold":
                alert.auto_label = _("%(prod)s · avisar con %(qty)s o menos",
                                     prod=product, qty=alert.min_qty)
            else:
                alert.auto_label = _("%(prod)s · %(freq)s",
                                     prod=product, freq=alert._mgs_interval_label())

    @api.depends("name", "auto_label")
    def _compute_display_name(self):
        for alert in self:
            alert.display_name = alert.name or alert.auto_label

    @api.depends("product_id.qty_available", "min_qty", "alert_type")
    def _compute_is_triggered(self):
        for alert in self:
            alert.is_triggered = alert._mgs_is_below_threshold()

    @api.constrains("alert_type", "interval_number")
    def _check_interval_number(self):
        for alert in self:
            if alert.alert_type == "periodic" and alert.interval_type == "days" \
                    and alert.interval_number < 1:
                raise ValidationError(_("El intervalo en días debe ser 1 o más."))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _mgs_is_below_threshold(self):
        self.ensure_one()
        if self.alert_type != "threshold" or not self.product_id:
            return False
        rounding = self.product_id.uom_id.rounding or 0.01
        return float_compare(self.product_id.qty_available, self.min_qty,
                             precision_rounding=rounding) <= 0

    def _mgs_interval_label(self):
        self.ensure_one()
        if self.interval_type == "weekly":
            return _("resumen semanal")
        if self.interval_type == "monthly":
            return _("resumen mensual")
        return _("resumen cada %s días", self.interval_number)

    def _mgs_next_due(self):
        """Fecha/hora a partir de la cual toca volver a avisar."""
        self.ensure_one()
        if not self.last_run:
            return fields.Datetime.now()
        if self.interval_type == "weekly":
            return self.last_run + relativedelta(weeks=1)
        if self.interval_type == "monthly":
            return self.last_run + relativedelta(months=1)
        return self.last_run + relativedelta(days=max(self.interval_number, 1))

    # ------------------------------------------------------------------
    # Cron: genera los avisos periodicos
    # ------------------------------------------------------------------
    @api.model
    def _mgs_cron_run_alerts(self):
        now = fields.Datetime.now()
        Notice = self.env["mgs.stock.alert.notice"]
        for alert in self.search([("alert_type", "=", "periodic")]):
            if alert._mgs_next_due() > now:
                continue
            message = _("%(prod)s: %(qty).0f uds. en stock (%(freq)s)",
                        prod=alert.product_id.name,
                        qty=alert.product_id.qty_available,
                        freq=alert._mgs_interval_label())
            if alert.name:
                message = "%s · %s" % (alert.name, message)
            Notice.create({
                "alert_id": alert.id,
                "product_id": alert.product_id.id,
                "name": message,
            })
            alert.last_run = now


class MgsStockAlertNotice(models.Model):
    """Aviso ya generado y pendiente de leer, mostrado en el panel de Stock.

    Solo se guardan los periodicos: los de cantidad se calculan en vivo desde
    `mgs.stock.alert` para que desaparezcan solos al reponer el producto.
    """
    _name = "mgs.stock.alert.notice"
    _description = "Aviso de stock generado"
    _order = "create_date desc, id desc"

    alert_id = fields.Many2one("mgs.stock.alert", string="Aviso", ondelete="cascade")
    product_id = fields.Many2one("product.template", string="Producto", required=True,
                                  ondelete="cascade")
    name = fields.Char("Mensaje", required=True)
    is_read = fields.Boolean("Leído", default=False)

    # Estos tres campos los rellena `PosOrder.mgs_authorize_deficit` (venta
    # con stock insuficiente autorizada desde el TPV) y, al sincronizarse el
    # ticket, `PosOrder._process_order`. `pos_order_id` puede tardar en
    # rellenarse (o quedar vacío si la venta nunca se confirma), por eso
    # también se guarda el uuid: es el enlace estable desde el primer momento.
    pos_order_id = fields.Many2one("pos.order", ondelete="set null", copy=False)
    pos_order_uuid = fields.Char(copy=False, index=True)
    session_id = fields.Many2one("pos.session", ondelete="set null", copy=False)

    def action_mark_read(self):
        self.write({"is_read": True})
        return True
