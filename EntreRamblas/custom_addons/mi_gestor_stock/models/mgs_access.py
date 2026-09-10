# -*- coding: utf-8 -*-
"""Acceso a la aplicación: una sola cuenta (la propietaria), contraseña,
recuperación por clave impresa y límite persistente de intentos.

Sin correo en el flujo, sin selector de usuario y sin contraseña maestra
compartida. El detalle de por qué está en `../ACCESO.md`.

Piezas:

  * `res.users` gana `mgs_is_owner` (la cuenta que sirve el formulario) y
    `mgs_password_set` (si la dueña ya fijó su contraseña o sigue pendiente
    del asistente de primer acceso).
  * `mgs.access` — registro único con la huella de la clave de recuperación
    y el estado del código de activación. Nunca guarda el secreto, solo su
    SHA-256.
  * `mgs.auth.throttle` — un contador por (ámbito, IP) que sobrevive a un
    reinicio: bloquea temporalmente tras varios fallos seguidos.
  * `mgs.access.event` — rastro de cada restablecimiento (quién, cuándo,
    por qué vía). Sin secretos.

Nada de este módulo escribe contraseñas ni claves en el log.
"""
import base64
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError

_logger = logging.getLogger(__name__)

# --- Política de contraseña -------------------------------------------------
MIN_PASSWORD_LENGTH = 12
_TRIVIAL = {
    "contrasena", "contraseña", "password", "passw0rd", "123456789012",
    "entreramblas", "floristeria", "floristería", "administrador", "propietaria",
}

# --- Formato de los secretos ---------------------------------------------------
_RECOVERY_BYTES = 20      # 160 bits (el plan pide >= 128)
_ACTIVATION_BYTES = 10    # 80 bits, código local de un solo uso


def _b32(raw):
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _group(code, size=4):
    return "-".join(code[i:i + size] for i in range(0, len(code), size))


def normalize_secret(value):
    """Deja el código como lo comparamos: solo letras y dígitos, en mayúsculas."""
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def fingerprint(value):
    return hashlib.sha256(normalize_secret(value).encode("ascii")).hexdigest()


def _humanize(seconds):
    seconds = max(1, int(seconds))
    if seconds < 90:
        return _("%s segundos", seconds)
    return _("%s minutos", max(1, round(seconds / 60)))


class ThrottleError(Exception):
    """Demasiados intentos. El controlador la traduce a una página, no a un 500."""

    def __init__(self, seconds):
        self.seconds = max(1, int(seconds))
        super().__init__("throttled")


class ResUsers(models.Model):
    _inherit = "res.users"

    mgs_is_owner = fields.Boolean(
        "Cuenta de propietaria", copy=False, default=False,
        help="La única cuenta que atiende el formulario de acceso. El servidor "
             "la elige sola; el formulario no permite cambiar de usuario.")
    mgs_password_set = fields.Boolean(
        "Contraseña establecida", copy=False, default=True,
        help="En falso mientras la dueña no haya completado el primer acceso "
             "con el código de activación.")

    @api.constrains("mgs_is_owner")
    def _check_single_owner(self):
        if self.search_count([("mgs_is_owner", "=", True)]) > 1:
            raise ValidationError(_("Solo puede haber una cuenta de propietaria."))

    @api.model
    def _mgs_owner(self):
        return self.sudo().search([("mgs_is_owner", "=", True)], limit=1)

    def _mgs_scramble_password(self):
        """Deja la cuenta sin contraseña utilizable (técnico / rotura de cristal)."""
        for user in self.sudo():
            user.write({"password": secrets.token_urlsafe(48)})


class MgsAccess(models.Model):
    _name = "mgs.access"
    _description = "Acceso y recuperación"

    name = fields.Char(default="Acceso de la tienda", readonly=True)

    activation_state = fields.Selection([
        ("none", "Sin usar"),
        ("pending", "Pendiente de primer acceso"),
        ("used", "Primer acceso completado"),
    ], default="none", readonly=True, copy=False)
    activation_fingerprint = fields.Char(readonly=True, copy=False, groups="base.group_system")

    recovery_fingerprint = fields.Char(readonly=True, copy=False, groups="base.group_system")
    recovery_generated_at = fields.Datetime("Clave de recuperación generada", readonly=True, copy=False)
    recovery_ack = fields.Boolean(
        "Custodia de la clave confirmada", readonly=True, copy=False,
        help="La dueña ha confirmado que guarda la clave fuera del ordenador.")

    has_recovery_key = fields.Boolean(compute="_compute_flags")
    recovery_hint = fields.Char(compute="_compute_flags")

    @api.depends("recovery_generated_at", "recovery_ack")
    def _compute_flags(self):
        for rec in self:
            fp = rec.sudo().recovery_fingerprint or ""
            rec.has_recovery_key = bool(rec.recovery_generated_at)
            rec.recovery_hint = (fp[:8] + "…") if fp else ""

    # ------------------------------------------------------------------
    @api.model
    def _get(self):
        model = self.sudo()
        rec = model.env.ref("mi_gestor_stock.mgs_access_default", raise_if_not_found=False)
        if not rec:
            rec = model.search([], limit=1)
        if not rec:
            rec = model.create({})
        return rec.sudo()

    @api.model
    def action_mgs_open(self):
        from .mgs_permissions import require_manager
        require_manager(self.env)
        rec = self._get()
        return {
            "type": "ir.actions.act_window",
            "name": _("Seguridad y acceso"),
            "res_model": "mgs.access",
            "res_id": rec.id,
            "view_mode": "form",
            "target": "current",
        }

    # ---- Política de contraseña --------------------------------------
    @api.model
    def _check_password_policy(self, password, login=None):
        password = password or ""
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(_(
                "La contraseña debe tener al menos %s caracteres.", MIN_PASSWORD_LENGTH))
        low = password.strip().lower()
        if login and low == (login or "").strip().lower():
            raise ValidationError(_("La contraseña no puede ser igual al nombre de la cuenta."))
        if len(set(password)) <= 2 or any(token in low for token in _TRIVIAL):
            raise ValidationError(_("Esa contraseña es demasiado fácil de adivinar. Elige otra."))
        return True

    # ---- Código de activación (primer acceso) -----------------------
    @api.model
    def _begin_activation(self, owner):
        """Genera el código de activación, guarda su huella y marca a la dueña
        como pendiente. Devuelve el código en claro (lo escribe el instalador,
        una sola vez, en <base>-activacion.txt)."""
        code = _group(_b32(secrets.token_bytes(_ACTIVATION_BYTES)))
        self._get().write({
            "activation_state": "pending",
            "activation_fingerprint": fingerprint(code),
            "recovery_fingerprint": False,
            "recovery_generated_at": False,
            "recovery_ack": False,
        })
        owner.sudo().write({"mgs_password_set": False})
        return code

    @api.model
    def _consume_activation(self, code, password, confirm):
        access = self._get()
        if access.activation_state != "pending" or not access.activation_fingerprint:
            raise UserError(_(
                "El primer acceso ya se completó. Usa «He olvidado mi contraseña» "
                "si necesitas entrar."))
        if not hmac.compare_digest(fingerprint(code), access.activation_fingerprint):
            raise UserError(_("El código de activación no es correcto."))
        if password != confirm:
            raise ValidationError(_("Las dos contraseñas no coinciden."))
        owner = self.env["res.users"]._mgs_owner()
        if not owner:
            raise UserError(_("No hay ninguna cuenta de propietaria configurada."))
        self._check_password_policy(password, owner.login)
        owner.sudo().write({"password": password, "mgs_password_set": True})
        access.write({"activation_state": "used", "activation_fingerprint": False})
        self._log_event("primer-acceso", _("Primer acceso completado; contraseña establecida."))
        return self._new_recovery_key()

    # ---- Clave de recuperación -------------------------------------
    @api.model
    def _new_recovery_key(self):
        """Rota la clave: genera una nueva, guarda solo su huella e invalida la
        anterior. Devuelve la clave en claro para enseñarla UNA vez."""
        key = _group(_b32(secrets.token_bytes(_RECOVERY_BYTES)))
        self._get().write({
            "recovery_fingerprint": fingerprint(key),
            "recovery_generated_at": fields.Datetime.now(),
            "recovery_ack": False,
        })
        return key

    @api.model
    def _verify_recovery_key(self, key):
        fp = self._get().recovery_fingerprint
        return bool(fp) and hmac.compare_digest(fingerprint(key), fp)

    @api.model
    def _recover_with_key(self, key, password, confirm):
        """Comprueba la clave, cambia la contraseña, invalida sesiones y rota la
        clave. Devuelve la clave nueva para enseñarla una vez."""
        if not self._verify_recovery_key(key):
            raise UserError(_("La clave de recuperación no es correcta."))
        if password != confirm:
            raise ValidationError(_("Las dos contraseñas no coinciden."))
        owner = self.env["res.users"]._mgs_owner()
        if not owner:
            raise UserError(_("No hay ninguna cuenta de propietaria configurada."))
        self._check_password_policy(password, owner.login)
        owner.sudo().write({"password": password, "mgs_password_set": True})
        # Cambiar la contraseña ya invalida el resto de sesiones (el token de
        # sesión de Odoo se deriva del hash de la contraseña). Se limpia además
        # la caché del registro para no servir ninguna sesión cacheada.
        self.env.registry.clear_cache()
        new_key = self._new_recovery_key()
        self._log_event("recuperar", _("Contraseña restablecida con la clave de recuperación."))
        return new_key

    @api.model
    def _mark_recovery_ack(self):
        self._get().write({"recovery_ack": True})

    def action_regenerate_recovery_key(self):
        """Botón de Configuración → Seguridad. Exige la contraseña actual: abre
        el asistente `mgs.access.regenerate`."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Regenerar la clave de recuperación"),
            "res_model": "mgs.access.regenerate",
            "view_mode": "form",
            "target": "new",
        }

    # ---- Rastro de restablecimientos -------------------------------
    @api.model
    def _log_event(self, source, note):
        self.env["mgs.access.event"].sudo().create({"source": source, "note": note})
        _logger.info("mi_gestor_stock: acceso — %s (%s)", note, source)


class MgsAccessEvent(models.Model):
    _name = "mgs.access.event"
    _description = "Restablecimientos de acceso"
    _order = "create_date desc"

    source = fields.Selection([
        ("primer-acceso", "Primer acceso"),
        ("recuperar", "Clave de recuperación"),
        ("configuracion", "Configuración → Seguridad"),
        ("herramienta-local", "Herramienta local (administrador de Windows)"),
    ], required=True, readonly=True)
    note = fields.Char(required=True, readonly=True)

    def write(self, vals):
        raise UserError(_("El rastro de restablecimientos no se puede modificar."))

    def unlink(self):
        raise UserError(_("El rastro de restablecimientos no se puede borrar."))


class MgsAuthThrottle(models.Model):
    _name = "mgs.auth.throttle"
    _description = "Límite persistente de intentos de acceso"

    scope = fields.Char(required=True, index=True)
    client = fields.Char(required=True, index=True)
    failures = fields.Integer(default=0)
    window_start = fields.Datetime()
    locked_until = fields.Datetime()

    _sql_constraints = [(
        "scope_client_uniq", "unique(scope, client)",
        "Ya hay un contador para este cliente y ámbito.",
    )]

    # Política: 5 fallos en 15 min -> bloqueo, que se dobla desde 60 s.
    _MAX_FAILURES = 5
    _WINDOW_SECONDS = 900
    _LOCK_BASE_SECONDS = 60
    _LOCK_MAX_STEPS = 6

    @api.model
    def _client_key(self):
        from odoo.http import request
        if not request:
            return "local"
        # App local monousuario: no hay proxy de confianza, se usa la IP directa.
        return request.httprequest.remote_addr or "?"

    @api.model
    def _row(self, scope):
        return self.sudo().search(
            [("scope", "=", scope), ("client", "=", self._client_key())], limit=1)

    @api.model
    def _assert_open(self, scope):
        row = self._row(scope)
        now = fields.Datetime.now()
        if row and row.locked_until and row.locked_until > now:
            raise ThrottleError((row.locked_until - now).total_seconds())
        return row

    @api.model
    def _register_failure(self, scope):
        """Nunca lanza: solo cuenta el fallo y, si toca, fija el bloqueo."""
        now = fields.Datetime.now()
        row = self._row(scope)
        if not row:
            row = self.sudo().create({
                "scope": scope, "client": self._client_key(),
                "window_start": now, "failures": 0,
            })
        locked = row.locked_until and row.locked_until > now
        if not locked and row.window_start and \
                (now - row.window_start).total_seconds() > self._WINDOW_SECONDS:
            row.window_start = now
            row.failures = 0
        row.failures += 1
        if row.failures >= self._MAX_FAILURES:
            step = min(row.failures - self._MAX_FAILURES, self._LOCK_MAX_STEPS)
            row.locked_until = now + timedelta(seconds=self._LOCK_BASE_SECONDS * (2 ** step))

    @api.model
    def _register_success(self, scope):
        row = self._row(scope)
        if row:
            row.unlink()

    @api.autovacuum
    def _gc_stale(self):
        horizon = fields.Datetime.now() - timedelta(days=7)
        self.sudo().search([
            "&",
            "|", ("locked_until", "=", False), ("locked_until", "<", horizon),
            ("write_date", "<", horizon),
        ]).unlink()


class MgsAccessRegenerate(models.TransientModel):
    _name = "mgs.access.regenerate"
    _description = "Regenerar la clave de recuperación"

    current_password = fields.Char("Contraseña actual", required=True)
    new_key = fields.Char("Nueva clave", readonly=True)
    done = fields.Boolean(readonly=True)

    def action_confirm(self):
        self.ensure_one()
        from .mgs_permissions import require_manager
        require_manager(self.env)
        try:
            self.env.user._check_credentials(
                {"type": "password", "password": self.current_password},
                {"interactive": True})
        except AccessDenied:
            raise UserError(_("La contraseña actual no es correcta."))
        key = self.env["mgs.access"].sudo()._new_recovery_key()
        self.env["mgs.access"].sudo()._log_event(
            "configuracion", _("Clave de recuperación regenerada desde Configuración → Seguridad."))
        self.write({"new_key": key, "done": True})
        return {
            "type": "ir.actions.act_window",
            "res_model": "mgs.access.regenerate",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
