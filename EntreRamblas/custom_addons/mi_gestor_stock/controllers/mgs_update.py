# -*- coding: utf-8 -*-
"""El acceso directo del escritorio (`instalador/abrir-app.ps1`) avisa aquí de
que alguien está entrando al programa: si hay una versión firmada más nueva,
se instala antes de abrir la ventana. Ver `mgs.update._mgs_auto_on_enter`."""
import ipaddress

from odoo import http
from odoo.http import request


class MgsUpdateController(http.Controller):

    # auth="public": el lanzador no tiene sesión (la base sale del dbfilter).
    # readonly=False: con un cursor de solo lectura Odoo podría repetir la
    # función entera, y lanzaría dos veces el proceso de fondo.
    @http.route("/mgs/actualizacion/al-entrar", type="http", auth="public", methods=["POST"],
                csrf=False, sitemap=False, readonly=False)
    def mgs_update_on_enter(self, **kw):
        # Solo el propio equipo. El servidor ya escucha únicamente en
        # 127.0.0.1 (odoo.local); esto es la segunda barrera.
        try:
            local = ipaddress.ip_address(request.httprequest.remote_addr or "").is_loopback
        except ValueError:
            local = False
        if not local:
            return request.make_json_response({"error": "solo-local"}, status=403)
        return request.make_json_response(request.env["mgs.update"].sudo()._mgs_auto_on_enter())
