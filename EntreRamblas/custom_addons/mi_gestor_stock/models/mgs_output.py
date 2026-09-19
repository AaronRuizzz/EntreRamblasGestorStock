# -*- coding: utf-8 -*-
"""Carpetas de salida para lo que genera el programa.

Antes, todo lo que se podía descargar (informe mensual, CSV de estadísticas,
factura...) salía como `ir.actions.act_url` con `target: "download"`: el
navegador lo dejaba en la carpeta de Descargas del sistema, todo junto y sin
distinguir qué es un informe y qué es una factura. El servidor corre en el
mismo PC que la tienda, así que puede escribir el archivo él mismo en la
carpeta que toque — ver mgs.config.output_dir (pestaña «Carpetas de salida»
de Configuración → Dispositivos) y `_mgs_save_output` más abajo, que es el
único punto de escritura para no repetir la lógica de nombres/carpetas en
cada informe o ticket.
"""
import os

from odoo import api, fields, models
from odoo.exceptions import UserError

from .mgs_permissions import require_manager

# Subcarpetas fijas dentro de la carpeta configurada. Así nunca se mezclan
# los documentos para consulta/gestoría, las facturas fiscales y los tickets.
SUBFOLDERS = {"informes": "Informes", "facturas": "Facturas", "tickets": "Tickets"}


class MgsConfig(models.Model):
    _inherit = "mgs.config"

    output_dir = fields.Char(
        "Carpeta de informes y facturas",
        default=lambda self: self._mgs_default_output_dir(),
        help="Dentro se crean, si no existen, las subcarpetas «Informes», "
             "«Facturas» y «Tickets». Vacía: se usa la carpeta «Documentos\\Entre "
             "Ramblas» del usuario que ejecuta el servidor.")
    output_invoices_dir = fields.Char(
        "Carpeta de facturas", compute="_compute_output_directories", readonly=True)
    output_reports_dir = fields.Char(
        "Carpeta de informes", compute="_compute_output_directories", readonly=True)
    output_tickets_dir = fields.Char(
        "Carpeta de tickets", compute="_compute_output_directories", readonly=True)

    @api.model
    def _mgs_default_output_dir(self):
        return os.path.join(os.path.expanduser("~"), "Documents", "Entre Ramblas")

    @api.depends("output_dir")
    def _compute_output_directories(self):
        """Muestra las rutas finales sin crear archivos al abrir Ajustes."""
        for config in self:
            base = (config.output_dir or "").strip() or config._mgs_default_output_dir()
            config.output_invoices_dir = os.path.join(base, SUBFOLDERS["facturas"])
            config.output_reports_dir = os.path.join(base, SUBFOLDERS["informes"])
            config.output_tickets_dir = os.path.join(base, SUBFOLDERS["tickets"])

    def _mgs_output_dir(self, kind):
        """Ruta absoluta de la subcarpeta `kind` («informes» o «facturas»),
        creándola (y la carpeta base) si todavía no existe."""
        self.ensure_one()
        base = (self.output_dir or "").strip() or self._mgs_default_output_dir()
        directory = os.path.join(base, SUBFOLDERS[kind])
        os.makedirs(directory, exist_ok=True)
        return directory

    def _mgs_save_output(self, kind, filename, content):
        """Escribe `content` (bytes) en la carpeta de `kind` con `filename`.

        Si ese nombre ya existe se prueba con «-2», «-3»... en vez de
        sobrescribir: dos informes del mismo periodo generados en momentos
        distintos (una corrección, una segunda copia para la gestoría) tienen
        que quedar los dos, no que el segundo borre el primero.
        """
        self.ensure_one()
        directory = self._mgs_output_dir(kind)
        base_name, ext = os.path.splitext(filename)
        path = os.path.join(directory, filename)
        counter = 2
        while os.path.exists(path):
            path = os.path.join(directory, "%s-%d%s" % (base_name, counter, ext))
            counter += 1
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def action_mgs_prepare_output_folders(self):
        """Crea las dos carpetas antes de generar el primer documento."""
        self.ensure_one()
        require_manager(self.env)
        try:
            invoices = self._mgs_output_dir("facturas")
            reports = self._mgs_output_dir("informes")
            tickets = self._mgs_output_dir("tickets")
        except OSError as err:
            raise UserError(self.env._("No se han podido preparar las carpetas: %s", err)) from err
        return self._mgs_notify(self.env._(
            "Carpetas preparadas. Facturas: %s | Informes: %s | Tickets: %s",
            invoices, reports, tickets))

    def _mgs_open_output_folder(self, kind):
        self.ensure_one()
        require_manager(self.env)
        directory = self._mgs_output_dir(kind)
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise UserError(self.env._(
                "Esta función abre carpetas desde Windows. La carpeta está en: %s", directory))
        try:
            os.startfile(directory)  # noqa: S606 - carpeta local elegida en Ajustes, Windows únicamente.
        except OSError as err:
            raise UserError(self.env._("No se ha podido abrir la carpeta: %s", err)) from err
        return self._mgs_notify(self.env._("Carpeta abierta: %s", directory))

    def action_mgs_open_invoices_folder(self):
        return self._mgs_open_output_folder("facturas")

    def action_mgs_open_reports_folder(self):
        return self._mgs_open_output_folder("informes")

    def action_mgs_open_tickets_folder(self):
        return self._mgs_open_output_folder("tickets")
