# -*- coding: utf-8 -*-
"""Acceso solo con contraseña, primer acceso con código y recuperación por
clave impresa. Ver `models/mgs_access.py` y `ACCESO.md`.

Reglas:
  * el formulario de `/web/login` no lleva selección de usuario: en cuanto la
    dueña ha fijado su contraseña, el servidor autentica SIEMPRE su cuenta y
    descarta cualquier `login` que llegue en la petición;
  * mientras el primer acceso está pendiente, `/web/login` redirige al
    asistente protegido por el código de activación;
  * no hay recuperación por correo: el enlace lleva a `/mgs/recuperar`, que
    pide la clave impresa;
  * intentos limitados de forma persistente (sobreviven a un reinicio) y
    CSRF en cada formulario;
  * ni contraseñas ni claves llegan al log.
"""
import hmac
import logging
import secrets

from odoo import _, http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db

from ..models.mgs_access import ThrottleError
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

FIRST_ACCESS_URL = "/mgs/primer-acceso"
RECOVER_URL = "/mgs/recuperar"
KEY_URL = "/mgs/clave-recuperacion"


class MgsAuth(Home):

    # ------------------------------------------------------------------ helpers
    def _mgs_public_env(self):
        if request.env.uid is None:
            if request.session.uid is None:
                request.env["ir.http"]._auth_method_public()
            else:
                request.update_env(user=request.session.uid)

    def _owner(self):
        return request.env["res.users"].sudo()._mgs_owner()

    def _access(self):
        return request.env["mgs.access"].sudo()._get()

    def _throttle(self):
        return request.env["mgs.auth.throttle"].sudo()

    def _wait_message(self, err):
        from ..models.mgs_access import _humanize
        return _("Demasiados intentos fallidos. Espera %s y vuelve a probar.",
                 _humanize(err.seconds))

    def _render(self, template, **values):
        values.setdefault("disable_footer", True)
        response = request.render(template, values)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    def _finish_and_show_key(self, key, first_time):
        """Cierra la sesión, la ROTA y deja la clave en la sesión nueva para
        enseñarla en una petición aparte (GET). Así el formulario de
        confirmación de custodia lleva un `csrf_token` de la sesión definitiva
        y no de la que se está descartando (hallazgo 13: el recorrido devolvía
        «Session expired (invalid CSRF token)»)."""
        request.session.logout(keep_db=True)
        request.session["mgs_recovery_key"] = key
        request.session["mgs_recovery_first"] = bool(first_time)
        request.session["mgs_key_ack_token"] = secrets.token_urlsafe(24)
        return request.redirect(KEY_URL)

    # ------------------------------------------------------------------- /web/login
    @http.route()
    def web_login(self, redirect=None, **kw):
        ensure_db()
        self._mgs_public_env()
        owner = self._owner()

        if owner and not owner.mgs_password_set and self._access().activation_state == "pending":
            return request.redirect(FIRST_ACCESS_URL)

        strict = bool(owner and owner.mgs_password_set)
        if request.httprequest.method != "POST":
            return super().web_login(redirect=redirect, **kw)

        throttle = self._throttle()
        try:
            throttle._assert_open("login")
        except ThrottleError as err:
            return self._render("web.login", error=self._wait_message(err),
                                databases=None, disable_database_manager=True)

        if strict:
            # El servidor elige la cuenta. Se ignora cualquier `login` recibido.
            request.params["login"] = owner.login

        response = super().web_login(redirect=redirect, **kw)
        if request.params.get("login_success"):
            throttle._register_success("login")
        else:
            throttle._register_failure("login")
        return response

    # -------------------------------------------------------- /mgs/primer-acceso
    @http.route(FIRST_ACCESS_URL, type="http", auth="none", sitemap=False)
    def mgs_first_access(self, **post):
        ensure_db()
        self._mgs_public_env()
        owner = self._owner()
        access = self._access()

        if not owner or owner.mgs_password_set or access.activation_state != "pending":
            return request.redirect("/web/login")

        if request.httprequest.method != "POST":
            return self._render("mi_gestor_stock.mgs_first_access")

        throttle = self._throttle()
        try:
            throttle._assert_open("primer-acceso")
        except ThrottleError as err:
            return self._render("mi_gestor_stock.mgs_first_access", error=self._wait_message(err))

        code = (post.get("activation_code") or "").strip()
        password = post.get("password") or ""
        confirm = post.get("confirm_password") or ""
        try:
            key = request.env["mgs.access"].sudo()._consume_activation(code, password, confirm)
        except (UserError, ValidationError) as err:
            throttle._register_failure("primer-acceso")
            return self._render("mi_gestor_stock.mgs_first_access", error=err.args[0])
        throttle._register_success("primer-acceso")
        return self._finish_and_show_key(key, first_time=True)

    # ------------------------------------------------------------- /mgs/recuperar
    @http.route(RECOVER_URL, type="http", auth="none", sitemap=False)
    def mgs_recover(self, **post):
        ensure_db()
        self._mgs_public_env()
        owner = self._owner()
        access = self._access()

        if not owner:
            return request.redirect("/web/login")
        if not access.recovery_fingerprint:
            return self._render("mi_gestor_stock.mgs_recover", no_key=True)

        if request.httprequest.method != "POST":
            return self._render("mi_gestor_stock.mgs_recover")

        throttle = self._throttle()
        try:
            throttle._assert_open("recuperar")
        except ThrottleError as err:
            return self._render("mi_gestor_stock.mgs_recover", error=self._wait_message(err))

        key = (post.get("recovery_key") or "").strip()
        password = post.get("password") or ""
        confirm = post.get("confirm_password") or ""
        try:
            new_key = request.env["mgs.access"].sudo()._recover_with_key(key, password, confirm)
        except (UserError, ValidationError) as err:
            throttle._register_failure("recuperar")
            return self._render("mi_gestor_stock.mgs_recover", error=err.args[0])
        throttle._register_success("recuperar")
        return self._finish_and_show_key(new_key, first_time=False)

    # ------------------------------------------------- /mgs/clave-recuperacion
    @http.route(KEY_URL, type="http", auth="none", sitemap=False, methods=["GET"])
    def mgs_recovery_key_page(self, **kw):
        """Enseña la clave UNA vez, en una petición propia con la sesión ya
        rotada. Recargar no la vuelve a mostrar (se saca de la sesión)."""
        ensure_db()
        # Como el resto de rutas auth="none": sin esto, request.env.user queda
        # vacío tras el logout de _finish_and_show_key y la plantilla base
        # (que pide el estado de sesión) revienta con "Expected singleton".
        self._mgs_public_env()
        key = request.session.pop("mgs_recovery_key", None)
        if not key:
            return request.redirect("/web/login")
        first = request.session.pop("mgs_recovery_first", False)
        return self._render("mi_gestor_stock.mgs_recovery_key", key=key, first_time=first,
                            ack_token=request.session.get("mgs_key_ack_token") or "")

    # readonly=False: por defecto una ruta auth="none" arranca con un cursor
    # de solo lectura y, si escribe (aquí, _mark_recovery_ack), Odoo REPITE
    # toda la función con un cursor de escritura (http.py:_transactioning).
    # Como esta función CONSUME el token de un solo uso con session.pop(),
    # ese reintento silencioso lo encontraba ya retirado en el segundo
    # intento y nunca llegaba a marcar la custodia — sin ningún error visible.
    @http.route(KEY_URL + "/confirmar", type="http", auth="none", sitemap=False,
                methods=["POST"], readonly=False)
    def mgs_recovery_key_ack(self, **post):
        """Marca la custodia SOLO si esta sesión acaba de ver la clave (tiene el
        token de un solo uso) y la casilla está marcada. Mantiene CSRF. Una
        petición desde una sesión anónima cualquiera no marca nada."""
        ensure_db()
        self._mgs_public_env()
        # El token de un solo uso solo lo pone _finish_and_show_key tras un
        # primer acceso o una recuperación correctos. Una sesión anónima que
        # llame a esta ruta directamente no lo tiene.
        expected = request.session.pop("mgs_key_ack_token", None)
        submitted = post.get("ack_token") or ""
        if expected and post.get("ack") and hmac.compare_digest(str(expected), str(submitted)):
            request.env["mgs.access"].sudo()._mark_recovery_ack()
        return request.redirect("/web/login")
