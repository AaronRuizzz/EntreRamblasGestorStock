# -*- coding: utf-8 -*-
"""Ventana de la aplicación sobre el actualizador (`tools/actualizador.py`).

El actualizador es un proceso aparte, con su propio estado persistente en
`<data_dir>/actualizador/estado.json`. Este modelo sólo LEE ese archivo para
enseñar «Actualización disponible» en la pantalla de inicio y en
Configuración → Actualizaciones, y permite a la dueña pulsar «Actualizar al
cerrar» (deja aceptada la actualización; la aplica el servicio, no Odoo).
"""
import json
import logging
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)


def _state_path():
    return Path(config.get("data_dir") or ".") / "actualizador" / "estado.json"


def _read_state():
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class MgsUpdate(models.TransientModel):
    _name = "mgs.update"
    _description = "Actualizaciones"

    phase = fields.Char(readonly=True)
    available_version = fields.Char(readonly=True)
    installed_version = fields.Char(readonly=True)
    notes = fields.Text(readonly=True)
    accepted = fields.Boolean(readonly=True)
    message = fields.Char(readonly=True)
    checked_at = fields.Char(readonly=True)

    @api.model
    def _summary(self):
        """Lo que necesita la pantalla de inicio (sólo la responsable)."""
        state = _read_state()
        phase = state.get("fase")
        if phase in ("disponible", "preparado"):
            version = state.get("version_disponible")
            label = _("Actualización disponible: versión %s", version)
            if state.get("aceptada_por_duena"):
                label = _("Actualización %s: se instalará al cerrar", version)
            return {"available": True, "version": version, "label": label,
                    "accepted": bool(state.get("aceptada_por_duena")),
                    "phase": phase, "notes": state.get("notas") or state.get("mensaje") or ""}
        if phase == "fallo":
            return {"available": False, "phase": "fallo",
                    "label": _("La última actualización no se pudo aplicar"),
                    "notes": state.get("mensaje") or ""}
        return {"available": False, "phase": phase or "al-dia", "label": "", "notes": ""}

    @api.model
    def action_open(self):
        from .mgs_permissions import require_manager
        require_manager(self.env)
        state = _read_state()
        rec = self.create({
            "phase": state.get("fase") or "al-dia",
            "available_version": state.get("version_disponible") or "",
            "installed_version": state.get("version_instalada") or "",
            "notes": state.get("notas") and " ".join(state["notas"]) or state.get("mensaje") or "",
            "accepted": bool(state.get("aceptada_por_duena")),
            "message": state.get("mensaje") or "",
            "checked_at": state.get("comprobado_en") or "",
        })
        return {
            "type": "ir.actions.act_window", "name": _("Actualizaciones"),
            "res_model": "mgs.update", "res_id": rec.id, "view_mode": "form", "target": "new",
        }

    def _write_state(self, **changes):
        from .mgs_permissions import require_manager
        require_manager(self.env)
        path = _state_path()
        state = _read_state()
        if not state:
            raise UserError(_(
                "No hay ninguna actualización preparada por el servicio todavía."))
        state.update(changes)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def action_accept(self):
        self.ensure_one()
        state = _read_state()
        manifest = state.get("manifest") or {}
        version = state.get("version_disponible")
        sha256 = manifest.get("sha256")
        if not version or not sha256:
            raise UserError(_(
                "No hay ninguna actualización preparada para aceptar todavía."))
        self._write_state(aceptada_por_duena=True)
        # Consentimiento vinculado a ESTA versión y ESTE paquete exactos: el
        # servicio aplicador no se fía de `aceptada_por_duena` a secas (un
        # booleano en un archivo que la app puede escribir), solo de esto
        # cruzado contra el manifiesto que él mismo re-verifica.
        self._write_acceptance(version, sha256)
        self.env["mgs.access"].sudo()._log_event(
            "configuracion", _("La propietaria aceptó instalar la actualización al cerrar."))
        self._start_update_service()
        return {"type": "ir.actions.act_window_close"}

    def _write_acceptance(self, version, sha256):
        import json as _json
        path = _state_path().parent / "aceptacion.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json.dumps({
            "version": version, "sha256": sha256,
            "fecha": fields.Datetime.now().isoformat(),
            "usuario": self.env.user.login,
        }, ensure_ascii=False), encoding="utf-8")

    def _start_update_service(self):
        # «Se instalará al cerrar», de verdad: esto es lo que arranca el
        # componente con privilegios (tools/update_service.py). Él decide
        # CUÁNDO es seguro aplicar (sin caja abierta ni ventas en curso) y
        # reintenta durante horas si hace falta; aquí solo se le avisa.
        import subprocess
        try:
            subprocess.run(["sc", "start", "EntreRamblasActualizador"],
                           capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            _logger.warning(
                "mi_gestor_stock: no se pudo iniciar el servicio EntreRamblasActualizador; "
                "la actualización queda aceptada pero no se aplicará hasta el próximo "
                "arranque del servicio.", exc_info=True)

    def action_defer(self):
        self.ensure_one()
        self._write_state(aceptada_por_duena=False)
        return {"type": "ir.actions.act_window_close"}

    # ------------------------------------------------------------------
    # Comprobación diaria (además de la del arranque, que hace el servicio).
    # No aplica nada: sólo mira si hay una versión firmada más nueva y deja
    # el estado en el archivo. Sin `mgs.update.releases_url` configurado, no
    # hace nada. El actualizador es un proceso aparte.
    # ------------------------------------------------------------------
    @api.model
    def _cron_check(self):
        import subprocess
        import sys
        url = self.env["ir.config_parameter"].sudo().get_param("mgs.update.releases_url")
        if not url:
            return
        runtime = config.get("data_dir") or "."
        script = Path(__file__).resolve().parents[3] / "tools" / "actualizador.py"
        try:
            result = subprocess.run(
                [sys.executable, str(script), "--runtime", runtime, "comprobar",
                 "--releases-url", url],
                timeout=180, capture_output=True, check=False)
            # Si hay una versión nueva y compatible, descargarla y verificarla
            # YA (firma + SHA-256): cuando la dueña acepte, el paquete ya está
            # listo en disco y el servicio aplicador no tiene que esperar a
            # una descarga. `preparar` no instala nada por sí solo.
            output = (result.stdout or b"").decode("utf-8", "replace").strip()
            if output.startswith("disponible"):
                subprocess.run(
                    [sys.executable, str(script), "--runtime", runtime, "preparar",
                     "--releases-url", url],
                    timeout=300, capture_output=True, check=False)
        except (OSError, subprocess.SubprocessError):
            _logger.warning("mi_gestor_stock: no se pudo comprobar actualizaciones", exc_info=True)
