# -*- coding: utf-8 -*-
"""Carpetas de salida para lo que genera el programa (informes y facturas).

Antes, todo lo que se podía descargar (informe mensual, CSV de estadísticas,
factura...) salía como `ir.actions.act_url` con `target: "download"`: el
navegador lo dejaba en la carpeta de Descargas del sistema, todo junto y sin
distinguir qué es un informe y qué es una factura. El servidor corre en el
mismo PC que la tienda, así que puede escribir el archivo él mismo en la
carpeta que toque — ver mgs.config.output_dir (pestaña «Carpetas de salida»
de Configuración → Dispositivos) y `_mgs_save_output` más abajo, que es el
único punto de escritura para no repetir la lógica de nombres/carpetas en
cada informe.
"""
import os

from odoo import api, fields, models

# Subcarpetas fijas dentro de la carpeta configurada: una para lo que se
# genera para consulta/gestoría (informes), otra para lo que tiene validez
# fiscal (facturas) — así nunca se mezclan en el explorador de archivos.
SUBFOLDERS = {"informes": "Informes", "facturas": "Facturas"}


class MgsConfig(models.Model):
    _inherit = "mgs.config"

    output_dir = fields.Char(
        "Carpeta de informes y facturas",
        default=lambda self: self._mgs_default_output_dir(),
        help="Dentro se crean, si no existen, las subcarpetas «Informes» y "
             "«Facturas». Vacía: se usa la carpeta «Documentos\\Entre "
             "Ramblas» del usuario que ejecuta el servidor.")

    @api.model
    def _mgs_default_output_dir(self):
        return os.path.join(os.path.expanduser("~"), "Documents", "Entre Ramblas")

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
