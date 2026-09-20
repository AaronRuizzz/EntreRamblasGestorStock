# -*- coding: utf-8 -*-
"""18.0.7.9.0 — carpetas de documentos administradas, ticket simplificado y
correo de la tienda.

Idempotente (se puede repetir sin efectos dobles):

  * Documentos: `output_dir` pasa a la ubicación administrada
    `%ProgramData%/EntreRamblas/Documentos`; se crean `Facturas`, `Informes`
    y `Tickets`; y se COPIAN (nunca se mueven ni se borran) los documentos de
    la ruta antigua. Un nombre repetido con contenido distinto se guarda con
    sufijo «-2», «-3»...; con el mismo contenido no se vuelve a copiar.
  * Ticket: los precios que se muestran llevan IVA incluido
    (`pos.config.iface_tax_included = "total"`). Los impuestos de las
    ventas no se tocan.
  * Correo: `entreramblasclavelyazahar@gmail.com` como correo visible de la
    empresa y su contacto, solo si estaban vacíos o eran el marcador técnico
    `tienda@entreramblas.invalid`.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["mgs.config"]._mgs_migrate_documents_location()
    env["mgs.access"]._mgs_ensure_company_sender()
    configs = env["pos.config"].search([("iface_tax_included", "!=", "total")])
    if configs:
        configs.write({"iface_tax_included": "total"})
    _logger.info("mi_gestor_stock: actualizado a 18.0.7.9.0 (documentos, ticket simplificado, correo).")
