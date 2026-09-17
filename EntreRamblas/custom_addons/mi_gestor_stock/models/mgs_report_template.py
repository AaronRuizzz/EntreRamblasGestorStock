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
from .mgs_permissions import require_manager

GESTORIA_XML_ID = "mi_gestor_stock.mgs_report_template_gestoria_completa"

SECTION_FIELDS = (
    "section_resumen", "section_ventas", "section_devoluciones", "section_cobros",
    "section_mermas", "section_stock", "section_consumo", "section_eventos",
    "section_correcciones",
)
FILTER_FIELDS = ("category_ids", "product_ids", "payment_method_ids")
# Lo único que se puede tocar en una plantilla bloqueada: necesita un periodo
# nuevo cada vez que se genera, pero nada más sobre ella puede cambiar.
LOCKED_ALLOWED_WRITE_FIELDS = {"date_from", "date_to"}


class MgsReportTemplate(models.Model):
    _name = "mgs.report.template"
    _description = "Plantilla de informe personalizado"
    _order = "is_locked desc, name"

    name = fields.Char(required=True)
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
        return super().write(vals)

    def unlink(self):
        require_manager(self.env)
        if any(record.is_locked for record in self) and not self.env.su:
            raise AccessError(_("«Gestoría completa» se conserva: no se puede eliminar."))
        return super().unlink()
