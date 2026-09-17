# -*- coding: utf-8 -*-
"""Plantillas de informes personalizados (Informes → Informes personalizados).

Una plantilla es un registro persistente reutilizable: periodo, secciones a
incluir, filtros (categorías/productos/métodos de pago) y orden. La plantilla
«Gestoría completa» (sembrada en data/mgs_report_template_data.xml) es la
única que puede presentarse como informe para la gestoría: lleva `is_locked`
y, mientras lo tenga, `write()` rechaza cualquier cambio que no sea el
periodo, para todo el mundo, incluido el superusuario. Así queda
estructuralmente incapaz de excluir ventas: no hay ninguna combinación de
permisos que permita añadirle un filtro o desmarcarle una sección.

El resto de plantillas son siempre «informe parcial para análisis interno»:
esa etiqueta se decide mirando `is_locked` (y la identidad del registro
sembrado), nunca "si los filtros están vacíos" — una plantilla nueva sin
filtros no puede hacerse pasar por la de gestoría.
"""
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from . import mgs_report_engine
from .mgs_permissions import require_manager

GESTORIA_XML_ID = "mi_gestor_stock.mgs_report_template_gestoria_completa"

GESTORIA_BANNER = "INFORME PARA GESTORÍA · GESTORÍA COMPLETA"
PARTIAL_BANNER = "INFORME PARCIAL PARA ANÁLISIS INTERNO"

SECTION_FIELDS = (
    "section_resumen", "section_ventas", "section_devoluciones", "section_cobros",
    "section_mermas", "section_stock", "section_consumo", "section_eventos",
    "section_correcciones",
)
FILTER_FIELDS = ("category_ids", "product_ids", "payment_method_ids")
# Lo que, al cambiar, deja obsoleta la vista previa guardada.
STALE_TRIGGER_FIELDS = {"date_from", "date_to", "group_by", "order_by"} \
    | set(SECTION_FIELDS) | set(FILTER_FIELDS)
# Lo único que se puede tocar en una plantilla bloqueada: necesita un periodo
# nuevo cada vez que se genera, pero nada más sobre ella puede cambiar.
LOCKED_ALLOWED_WRITE_FIELDS = {"date_from", "date_to"}


class MgsReportTemplate(models.Model):
    _name = "mgs.report.template"
    _description = "Plantilla de informe personalizado"
    _order = "is_locked desc, name"

    name = fields.Char("Nombre del informe", required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda s: s.env.company)
    date_from = fields.Date("Desde", required=True, default=lambda s: s._default_from())
    date_to = fields.Date("Hasta", required=True, default=lambda s: s._default_to())

    section_resumen = fields.Boolean("Resumen", default=True)
    section_ventas = fields.Boolean("Ventas", default=True)
    section_devoluciones = fields.Boolean("Devoluciones", default=True)
    section_cobros = fields.Boolean("Cobros", default=True)
    section_mermas = fields.Boolean("Mermas", default=True)
    section_stock = fields.Boolean("Stock", default=True)
    section_consumo = fields.Boolean("Consumo de flor", default=True)
    section_eventos = fields.Boolean("Eventos", default=True)
    section_correcciones = fields.Boolean("Correcciones", default=True)

    category_ids = fields.Many2many("product.category", string="Categorías")
    product_ids = fields.Many2many("product.product", string="Productos")
    payment_method_ids = fields.Many2many("pos.payment.method", string="Métodos de pago")

    # Solo afectan a las tablas de detalle de ventas/devoluciones/cobros; el
    # resto de secciones tienen un orden natural propio y lo ignoran.
    group_by = fields.Selection([
        ("none", "Sin agrupar"), ("day", "Día"), ("week", "Semana"), ("month", "Mes"),
        ("product", "Producto"), ("category", "Categoría"), ("payment_method", "Método de pago"),
    ], default="day", required=True, string="Agrupar por")
    order_by = fields.Selection([
        ("date_asc", "Fecha (antigua a reciente)"), ("date_desc", "Fecha (reciente a antigua)"),
        ("amount_asc", "Importe (menor a mayor)"), ("amount_desc", "Importe (mayor a menor)"),
    ], default="date_desc", required=True, string="Ordenar por")

    is_locked = fields.Boolean("Gestoría completa (bloqueada)", readonly=True, copy=False)
    is_gestoria_master = fields.Boolean(compute="_compute_is_gestoria_master")

    xlsx_file = fields.Binary(readonly=True, attachment=False)
    xlsx_filename = fields.Char(readonly=True)

    # --- Vista previa -------------------------------------------------
    # Campos guardados, NO calculados: recalcular estas cifras en cada
    # lectura haría que abrir la lista de plantillas lanzara el informe
    # entero de cada una. Se rellenan solo al pulsar «Actualizar vista
    # previa» (action_refresh_preview) y se marcan como caducadas en cuanto
    # cambia un filtro.
    preview_generated_at = fields.Datetime("Vista previa generada", readonly=True, copy=False)
    preview_stale = fields.Boolean("Vista previa desactualizada", default=True,
                                   readonly=True, copy=False)
    preview_line_ids = fields.One2many("mgs.report.preview.line", "template_id",
                                       "Filas de la vista previa", readonly=True, copy=False)
    review_line_ids = fields.One2many("mgs.report.sale.review", "template_id",
                                      "Preparación de ventas", readonly=True, copy=False)
    preview_sales_count = fields.Integer("Ventas (líneas)", readonly=True, copy=False)
    preview_sales_total = fields.Float("Ventas (importe)", readonly=True, copy=False)
    preview_refunds_count = fields.Integer("Devoluciones (líneas)", readonly=True, copy=False)
    preview_refunds_total = fields.Float("Devoluciones (importe)", readonly=True, copy=False)
    preview_payments_net = fields.Float("Cobros netos", readonly=True, copy=False)
    preview_scrap_cost = fields.Float("Coste de mermas", readonly=True, copy=False)
    preview_stock_value = fields.Float("Valor de stock", readonly=True, copy=False)
    preview_consumption_cost = fields.Float("Coste del consumo", readonly=True, copy=False)
    preview_events_count = fields.Integer("Eventos", readonly=True, copy=False)
    preview_corrections_count = fields.Integer("Correcciones", readonly=True, copy=False)

    def _compute_is_gestoria_master(self):
        master = self.env.ref(GESTORIA_XML_ID, raise_if_not_found=False)
        for record in self:
            record.is_gestoria_master = bool(record.is_locked and master and record.id == master.id)

    @api.model
    def _default_from(self):
        return fields.Date.context_today(self).replace(day=1)

    @api.model
    def _default_to(self):
        first = fields.Date.context_today(self).replace(day=1)
        return first + relativedelta(months=1, days=-1)

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_("Selecciona un periodo válido: la fecha inicial no puede superar la final."))

    def _mgs_check_gestoria_integrity(self):
        """Defensa en profundidad: además del candado de `write()`, cualquier
        punto de entrada de lectura (vista previa, Excel, PDF) vuelve a
        comprobar que la plantilla bloqueada de verdad incluye todo. Si esto
        alguna vez fallara (un bug futuro, una edición directa en base de
        datos), se corta aquí en vez de generar un informe que podría
        confundirse con el oficial."""
        self.ensure_one()
        if not self.is_locked:
            return
        if not all(self[field] for field in SECTION_FIELDS):
            raise UserError(_("«Gestoría completa» no puede tener secciones desactivadas."))
        if any(self[field] for field in FILTER_FIELDS):
            raise UserError(_(
                "«Gestoría completa» no puede tener filtros de categoría, producto ni método de pago."))

    @api.model_create_multi
    def create(self, vals_list):
        require_manager(self.env)
        for vals in vals_list:
            if vals.get("is_locked") and not self.env.su:
                raise AccessError(_("Solo el sistema puede crear una plantilla bloqueada."))
            if vals.get("is_locked") and self.search_count([
                    ("is_locked", "=", True),
                    ("company_id", "=", vals.get("company_id", self.env.company.id)),
            ]):
                raise UserError(_("Ya existe una plantilla «Gestoría completa» para esta empresa."))
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Vista previa
    # ------------------------------------------------------------------
    def _mgs_write_server_fields(self, vals):
        """Escritura de los campos que rellena el propio servidor (vista
        previa y archivo generado). Se salta el candado de `write()`, que
        está ahí para frenar ediciones del USUARIO sobre la plantilla
        bloqueada, no para impedir que su vista previa o su Excel se
        actualicen."""
        return super(MgsReportTemplate, self).write(vals)

    @api.onchange("date_from", "date_to", "category_ids", "product_ids",
                  "payment_method_ids", "group_by", "order_by", *SECTION_FIELDS)
    def _onchange_mark_preview_stale(self):
        self.preview_stale = True

    def action_refresh_preview(self):
        self.ensure_one()
        require_manager(self.env)
        data = mgs_report_engine.build(self)
        ventas = data.get("ventas", [])
        devoluciones = data.get("devoluciones", [])
        cobros = data.get("cobros", [])
        mermas = data.get("mermas", [])
        consumo = data.get("consumo", [])
        eventos = data.get("eventos") or {}
        correcciones = data.get("correcciones", [])
        self._mgs_write_server_fields({
            "preview_generated_at": fields.Datetime.now(),
            "preview_stale": False,
            "preview_sales_count": len(ventas),
            "preview_sales_total": sum(row["amount"] for row in ventas),
            "preview_refunds_count": len(devoluciones),
            "preview_refunds_total": sum(row["amount"] for row in devoluciones),
            "preview_payments_net": sum(row["received"] - row["returned"] for row in cobros),
            "preview_scrap_cost": sum(row["cost"] for row in mermas),
            "preview_stock_value": data.get("stock_value", 0.0),
            "preview_consumption_cost": sum(row["cost"] for row in consumo),
            "preview_events_count": len(eventos.get("rows", [])),
            "preview_corrections_count": len(correcciones),
        })
        self.preview_line_ids.unlink()
        self.env["mgs.report.preview.line"].create(self._mgs_preview_lines(data))
        self.review_line_ids.unlink()
        review_domain = [
            ("company_id", "=", self.company_id.id), ("qty", ">", 0),
            ("order_id.date_order", ">=", data["start"]),
            ("order_id.date_order", "<", data["end"]),
            ("order_id.state", "in", mgs_report_engine.SOLD_STATES),
        ]
        if self.category_ids:
            review_domain.append(("product_id.categ_id", "child_of", self.category_ids.ids))
        if self.product_ids:
            review_domain.append(("product_id", "in", self.product_ids.ids))
        self.env["mgs.report.sale.review"].create([
            {"template_id": self.id, "line_id": line.id}
            for line in self.env["pos.order.line"].search(review_domain)
        ])
        return True

    def _mgs_preview_lines(self, data):
        self.ensure_one()
        lines = []

        def add(section, label, date="", qty=0.0, amount=0.0, note=""):
            lines.append({
                "template_id": self.id, "section": section, "label": label or "—",
                "date": str(date or ""), "qty": qty, "amount": amount, "note": note or "",
            })

        for row in data.get("ventas", []):
            add("ventas", row["label"], qty=row["qty"], amount=row["amount"],
                note=_("%s operaciones") % row["count"])
        for row in data.get("devoluciones", []):
            add("devoluciones", row["product"], date=row["date"], qty=row["qty"],
                amount=row["amount"],
                note=_("%(original)s → %(devolucion)s") % {
                    "original": row["original_order"] or _("sin venta original"),
                    "devolucion": row["return_order"]})
        for row in data.get("cobros", []):
            add("cobros", row["name"], amount=row["received"] - row["returned"],
                note=_("%s movimientos") % row["count"])
        for row in data.get("mermas", []):
            add("mermas", row["product"], date=row["date"], qty=row["quantity"],
                amount=row["cost"], note=row["reason"])
        for row in data.get("stock", []):
            add("stock", row["name"], qty=row["qty"], amount=row["value"], note=row["uom"])
        for row in data.get("consumo", []):
            add("consumo", row["name"], qty=row["qty"], amount=row["cost"], note=row["uom"])
        for row in (data.get("eventos") or {}).get("rows", []):
            add("eventos", row["name"], date=row["date"], amount=row["total"], note=row["state"])
        for row in data.get("correcciones", []):
            add("correcciones", row.get("label", ""), date=row.get("date", ""),
                amount=row.get("amount", 0.0), note=row.get("note", ""))
        return lines

    # ------------------------------------------------------------------
    # Tablas del informe (las comparten el Excel y el PDF: una sola
    # definicion de que columnas lleva cada seccion, para que las dos
    # exportaciones no puedan discrepar)
    # ------------------------------------------------------------------
    def mgs_report_data(self):
        """Datos del informe para la plantilla QWeb del PDF (que no puede
        llamar funciones de módulo, solo métodos del registro)."""
        self.ensure_one()
        require_manager(self.env)
        return mgs_report_engine.build(self)

    def _mgs_banner(self):
        """El sello que llevan el Excel y el PDF. Depende de `is_locked` (y de
        la identidad del registro sembrado, vía `is_gestoria_master`), NUNCA
        de que los filtros estén vacíos: así una plantilla cualquiera no
        puede presentarse como el informe oficial para la gestoría."""
        self.ensure_one()
        return GESTORIA_BANNER if self.is_gestoria_master else PARTIAL_BANNER

    def action_print(self):
        self.ensure_one()
        require_manager(self.env)
        self._mgs_check_gestoria_integrity()
        return self.env.ref("mi_gestor_stock.action_report_mgs_report_builder").report_action(self)

    def _mgs_criteria_text(self):
        self.ensure_one()
        parts = [_("Periodo: %(desde)s a %(hasta)s") % {"desde": self.date_from, "hasta": self.date_to}]
        if self.category_ids:
            parts.append(_("Categorías: %s") % ", ".join(self.category_ids.mapped("display_name")))
        if self.product_ids:
            parts.append(_("Productos: %s") % ", ".join(self.product_ids.mapped("display_name")))
        if self.payment_method_ids:
            parts.append(_("Métodos de pago: %s") % ", ".join(self.payment_method_ids.mapped("name")))
        if not (self.category_ids or self.product_ids or self.payment_method_ids):
            parts.append(_("Sin filtros: todas las operaciones del periodo"))
        parts.append(_("Agrupado por: %s") % dict(self._fields["group_by"].selection)[self.group_by])
        parts.append(_("Orden: %s") % dict(self._fields["order_by"].selection)[self.order_by])
        return " · ".join(parts)

    def _mgs_sections(self, data):
        """Las secciones marcadas, en orden de lectura, con su tabla ya
        resuelta: (nombre de pestaña, cabeceras, filas)."""
        self.ensure_one()
        sections = []
        if self.section_resumen:
            resumen = data["resumen"]
            labels = [
                (_("Ventas antes de devoluciones, con impuestos"), "gross_sales_including_tax"),
                (_("Devoluciones con impuestos"), "refunds_including_tax"),
                (_("Ventas netas sin impuestos"), "total_revenue"),
                (_("Impuestos netos"), "taxes"),
                (_("Ventas netas con impuestos"), "sales_including_tax"),
                (_("Coste histórico vendido neto"), "total_cost_sold"),
                (_("Margen bruto"), "gross_profit"),
                (_("Tickets con venta"), "sale_ticket_count"),
                (_("Tickets con devolución"), "refund_ticket_count"),
                (_("Ticket medio de venta con impuestos"), "average_sale_ticket"),
                (_("Registros sin coste histórico"), "missing_costs"),
            ]
            sections.append((
                _("Resumen"),
                [_("Concepto"), _("Valor (%s)") % self.company_id.currency_id.name],
                [[label, resumen[key]] for label, key in labels]))
        if self.section_ventas:
            sections.append((
                _("Ventas"),
                [_("Concepto"), _("Unidades"), _("Importe sin impuestos"), _("Impuestos"),
                 _("Coste histórico"), _("Margen"), _("Operaciones")],
                [[row["label"], row["qty"], row["amount"], row["tax"], row["cost"],
                  row["amount"] - row["cost"], row["count"]] for row in data["ventas"]]))
        if self.section_devoluciones:
            sections.append((
                _("Devoluciones"),
                [_("Fecha"), _("Venta original"), _("Devolución"), _("Producto"),
                 _("Unidades"), _("Importe con impuestos"), _("Registrado por")],
                [[str(row["date"]), row["original_order"], row["return_order"], row["product"],
                  row["qty"], row["amount"], row["user"]] for row in data["devoluciones"]]))
        if self.section_cobros:
            if data.get("cobros_available"):
                rows = [[row["name"], row["received"], row["returned"],
                         row["received"] - row["returned"], row["deferred"], row["count"]]
                        for row in data["cobros"]]
            else:
                rows = [[_("Con filtro de categoría o producto no se pueden repartir los "
                           "cobros mixtos: quita el filtro para consultarlos."),
                         "", "", "", "", ""]]
            sections.append((
                _("Cobros"),
                [_("Método"), _("Entradas"), _("Salidas"), _("Neto"),
                 _("Cuenta cliente no cobrada"), _("Movimientos")],
                rows))
        if self.section_mermas:
            sections.append((
                _("Mermas"),
                [_("Fecha"), _("Referencia"), _("Producto"), _("Partida"), _("Motivo"),
                 _("Cantidad"), _("Unidad"), _("Registrado por"), _("Coste histórico")],
                [[row["date"], row["reference"], row["product"], row["lot"], row["reason"],
                  row["quantity"], row["uom"], row["recorded_by"], row["cost"]]
                 for row in data["mermas"]]))
        if self.section_stock:
            sections.append((
                _("Stock"),
                [_("Producto"), _("Cantidad"), _("Unidad"), _("Valor a coste"), _("Caduca")],
                [[row["name"], row["qty"], row["uom"], row["value"], str(row["expiry"] or "")]
                 for row in data["stock"]]))
        if self.section_consumo:
            sections.append((
                _("Consumo de flor"),
                [_("Producto"), _("Cantidad consumida"), _("Unidad"), _("Coste histórico")],
                [[row["name"], row["qty"], row["uom"], row["cost"]] for row in data["consumo"]]))
        if self.section_eventos:
            eventos = data["eventos"]
            sections.append((
                _("Eventos"),
                [_("Referencia"), _("Cliente"), _("Fecha"), _("Estado"), _("Total"),
                 _("Cobrado"), _("Pendiente"), _("Material sin devolver")],
                [[row["name"], row["partner"], str(row["date"]), row["state"], row["total"],
                  row["paid"], row["due"], row["pending_return"]] for row in eventos["rows"]]))
        if self.section_correcciones:
            sections.append((
                _("Correcciones"),
                [_("Fecha"), _("Referencia"), _("Tipo"), _("Operación original"),
                 _("Valor original"), _("Corrección"), _("Valor resultante"),
                 _("Motivo"), _("Confirmada por"), _("Resultado")],
                [[str(row.get("date", "")), row.get("name", ""), row.get("type", ""),
                  row.get("original", ""), row.get("original_value", 0.0),
                  row.get("corrected_value", 0.0), row.get("resulting_value", 0.0),
                  row.get("reason", ""), row.get("user", ""), row.get("note", "")]
                 for row in data["correcciones"]]))
        return sections

    def write(self, vals):
        require_manager(self.env)
        # `install_mode` lo pone SOLO el propio cargador de datos de Odoo
        # (Model._load_records, al reaplicar data/mgs_report_template_data.xml
        # en cada instalación/actualización del módulo) — nunca una acción de
        # usuario ni una llamada RPC normal. Sin esta excepción, un simple
        # `-u mi_gestor_stock` sobre una base donde el registro ya existe
        # rompería la propia instalación al reescribir sus valores de siempre.
        if not self.env.context.get("install_mode"):
            for record in self:
                if record.is_locked and set(vals) - LOCKED_ALLOWED_WRITE_FIELDS:
                    raise AccessError(_(
                        "«Gestoría completa» es una plantilla bloqueada: solo se puede "
                        "cambiar el periodo (desde/hasta); el resto no se modifica."))
        result = super().write(vals)
        # Cambiar el periodo o cualquier filtro deja obsoleto lo que muestra la
        # vista previa. Se marca también aquí (no solo en el onchange del
        # formulario) para que valga igual si el cambio llega por código o RPC.
        if set(vals) & STALE_TRIGGER_FIELDS:
            self._mgs_write_server_fields({"preview_stale": True})
        return result

    def unlink(self):
        require_manager(self.env)
        if any(record.is_locked for record in self) and not self.env.su:
            raise AccessError(_("«Gestoría completa» se conserva: no se puede eliminar."))
        return super().unlink()


class MgsReportPreviewLine(models.Model):
    """Filas de la vista previa de una plantilla. Son desechables: se borran
    y se vuelven a crear enteras en cada «Actualizar vista previa», así que
    no llevan candados ni trazabilidad — el dato de verdad está en las
    ventas, devoluciones y mermas de las que salen."""
    _name = "mgs.report.preview.line"
    _description = "Fila de la vista previa de un informe personalizado"
    _order = "section, id"

    template_id = fields.Many2one("mgs.report.template", required=True,
                                  ondelete="cascade", index=True)
    section = fields.Selection([
        ("ventas", "Ventas"), ("devoluciones", "Devoluciones"), ("cobros", "Cobros"),
        ("mermas", "Mermas"), ("stock", "Stock"), ("consumo", "Consumo de flor"),
        ("eventos", "Eventos"), ("correcciones", "Correcciones"),
    ], required=True, string="Sección")
    label = fields.Char("Concepto", required=True)
    # Char y no Date a propósito: aquí caben fechas de día, de semana, de mes
    # y etiquetas como «Todo el periodo», según cómo se agrupe el informe.
    date = fields.Char("Fecha")
    qty = fields.Float("Cantidad")
    amount = fields.Float("Importe")
    note = fields.Char("Detalle")
