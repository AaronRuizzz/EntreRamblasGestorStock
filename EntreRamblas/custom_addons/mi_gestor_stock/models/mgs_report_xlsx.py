# -*- coding: utf-8 -*-
"""Exportación a Excel de los informes personalizados: una pestaña por
sección elegida.

**Seguridad de celdas.** Aquí NUNCA se llama a `worksheet.write()`. Ese
método adivina el tipo por el contenido y convierte en FÓRMULA cualquier
texto que empiece por `=`, de modo que un producto llamado
`=HYPERLINK("http://...")` se ejecutaría al abrir el archivo. Todo pasa por
`_mgs_xlsx_write`, que elige explícitamente `write_string`, `write_number`,
`write_datetime` o `write_blank` según el tipo de Python: un texto acaba
siempre en una celda de texto, empiece por lo que empiece.

Por eso NO se repite aquí el truco del apóstrofo inicial que usa la
exportación a CSV (`mgs.monthly.report.action_export_all_csv`): allí hace
falta porque un CSV no lleva tipos de celda; aquí sobra, y ensuciaría los
nombres de los productos en la hoja.
"""
import base64
import io
import re

import xlsxwriter

from odoo import _, fields, models
from .mgs_permissions import require_manager
from . import mgs_report_engine

# Excel rechaza estos caracteres en el nombre de una pestaña, y la corta a 31.
INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


class MgsReportTemplate(models.Model):
    _inherit = "mgs.report.template"

    def _mgs_xlsx_write(self, worksheet, row, col, value, fmt=None):
        """Escribe una celda eligiendo el tipo a mano (ver la cabecera del
        módulo: es lo que impide que un nombre se convierta en fórmula)."""
        if value is None or value == "":
            return worksheet.write_blank(row, col, None, fmt)
        if isinstance(value, bool):
            return worksheet.write_string(row, col, _("Sí") if value else _("No"), fmt)
        if isinstance(value, str):
            return worksheet.write_string(row, col, value, fmt)
        if isinstance(value, (int, float)):
            return worksheet.write_number(row, col, value, fmt)
        # Fechas y fechas-hora: se pasan como texto ya formateado por Odoo
        # para no depender de la zona horaria del Excel de destino.
        return worksheet.write_string(row, col, str(value), fmt)

    def _mgs_sheet_name(self, name):
        return INVALID_SHEET_CHARS.sub(" ", name)[:31]

    def action_export_excel(self):
        self.ensure_one()
        require_manager(self.env)
        data = mgs_report_engine.build(self)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        banner_format = workbook.add_format({
            "bold": True, "font_color": "#FFFFFF",
            "bg_color": "#8B1A1A" if not self.is_gestoria_master else "#1F5C34"})
        header_format = workbook.add_format({"bold": True, "bg_color": "#EFEFEF", "border": 1})
        meta_format = workbook.add_format({"italic": True})

        banner = self._mgs_banner()
        for name, headers, rows in self._mgs_sections(data):
            worksheet = workbook.add_worksheet(self._mgs_sheet_name(name))
            worksheet.set_column(0, max(len(headers) - 1, 0), 22)
            self._mgs_xlsx_write(worksheet, 0, 0, banner, banner_format)
            self._mgs_xlsx_write(worksheet, 1, 0, _("Generado el %(fecha)s por %(autor)s") % {
                "fecha": fields.Datetime.context_timestamp(self, data["generated_at"]).strftime(
                    "%d/%m/%Y %H:%M"),
                "autor": data["author"]}, meta_format)
            self._mgs_xlsx_write(worksheet, 2, 0, self._mgs_criteria_text(), meta_format)
            for col, header in enumerate(headers):
                self._mgs_xlsx_write(worksheet, 4, col, header, header_format)
            for index, row in enumerate(rows):
                for col, value in enumerate(row):
                    self._mgs_xlsx_write(worksheet, 5 + index, col, value)
        workbook.close()

        self._mgs_write_server_fields({
            "xlsx_file": base64.b64encode(output.getvalue()),
            "xlsx_filename": "informe-%s-%s-%s.xlsx" % (
                re.sub(r"[^\w-]+", "-", self.name or "").strip("-").lower() or "personalizado",
                self.date_from, self.date_to),
        })
        return {"type": "ir.actions.act_url", "target": "download",
                "url": "/web/content/mgs.report.template/%s/xlsx_file/%s?download=true" % (
                    self.id, self.xlsx_filename)}
