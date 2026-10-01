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
from datetime import datetime, timezone
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


PHASE_LABELS = {
    "al-dia": "Al día",
    "disponible": "Actualización disponible",
    "preparado": "Lista para instalar",
    "aplicando": "Instalando…",
    "hecho": "Actualizada",
    "fallo": "Requiere atención",
}


class MgsUpdate(models.TransientModel):
    _name = "mgs.update"
    _description = "Actualizaciones"

    phase = fields.Char(readonly=True)
    phase_label = fields.Char("Estado", readonly=True)
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
        phase = state.get("fase") or "al-dia"
        # En «disponible/preparado» el mensaje del estado son las notas de la
        # versión; en el resto (sin conexión, fallo...) es un aviso.
        has_release_notes = phase in ("disponible", "preparado")
        rec = self.create({
            "phase": phase,
            "phase_label": PHASE_LABELS.get(phase, phase),
            # La versión «disponible» de un estado al día es la misma que la
            # instalada: solo tiene sentido enseñarla si es una novedad.
            "available_version": state.get("version_disponible") or "" if has_release_notes else "",
            "installed_version": state.get("version_instalada") or "",
            "notes": state.get("notas") and " ".join(state["notas"]) or state.get("mensaje") or "" if has_release_notes else "",
            "accepted": bool(state.get("aceptada_por_duena")),
            "message": "" if has_release_notes else state.get("mensaje") or "",
            "checked_at": self._format_checked_at(state.get("comprobado_en")),
        })
        return {
            "type": "ir.actions.act_window", "name": _("Actualizaciones"),
            "res_model": "mgs.update", "res_id": rec.id, "view_mode": "form", "target": "new",
        }

    @api.model
    def _format_checked_at(self, iso_value):
        """«21/09/2026 18:51» en hora local, en vez del ISO en UTC del estado."""
        if not iso_value:
            return _("Todavía no se ha comprobado")
        try:
            moment = datetime.fromisoformat(iso_value)
            if moment.tzinfo:
                moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
            return fields.Datetime.context_timestamp(self, moment).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return iso_value

    def action_check_now(self):
        """Botón «Buscar actualizaciones»: la misma comprobación que el cron
        diario, pero al momento. Solo COMPRUEBA (rápido, con firma); si hay una
        versión nueva, su descarga y verificación se lanzan en segundo plano
        para no dejar la pantalla bloqueada. No instala nada: eso sigue
        requiriendo «Actualizar al cerrar»."""
        from .mgs_permissions import require_manager
        require_manager(self.env)
        url = self.env["ir.config_parameter"].sudo().get_param("mgs.update.releases_url")
        if not url:
            raise UserError(_("No hay configurada una dirección de actualizaciones."))
        if not self._mgs_run_check(url, download_in_background=True):
            raise UserError(_(
                "No se ha podido comprobar las actualizaciones ahora mismo. "
                "Revisa la conexión a internet y vuelve a intentarlo."))
        return self.action_open()

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
        url = self.env["ir.config_parameter"].sudo().get_param("mgs.update.releases_url")
        if not url:
            return
        self._mgs_run_check(url, download_in_background=False)

    @api.model
    def _mgs_run_check(self, url, download_in_background):
        import subprocess
        import sys
        runtime = config.get("data_dir") or "."
        script = Path(__file__).resolve().parents[3] / "tools" / "actualizador.py"
        base = [sys.executable, str(script), "--runtime", runtime]
        # Dentro del servicio de Windows no hay consola: sin stdin propio el
        # proceso hijo se quedaba esperando hasta agotar el tiempo (la
        # comprobación tardaba 180 s en vez de ~1 s). Con la cuenta del
        # servicio, fuera de Odoo, responde en un segundo.
        quiet = {"stdin": subprocess.DEVNULL,
                 "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
        try:
            result = subprocess.run(
                base + ["comprobar", "--releases-url", url],
                timeout=60, capture_output=True, check=False, **quiet)
            # Si hay una versión nueva y compatible, descargarla y verificarla
            # YA (firma + SHA-256): cuando la dueña acepte, el paquete ya está
            # listo en disco y el servicio aplicador no tiene que esperar a
            # una descarga. `preparar` no instala nada por sí solo.
            output = (result.stdout or b"").decode("utf-8", "replace").strip()
            if output.startswith("disponible"):
                prepare = base + ["preparar", "--releases-url", url]
                if download_in_background:
                    # Descarga grande: sin esperar, para no bloquear el botón.
                    subprocess.Popen(prepare, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, **quiet)
                else:
                    subprocess.run(prepare, timeout=300, capture_output=True,
                                   check=False, **quiet)
            return output
        except (OSError, subprocess.SubprocessError):
            _logger.warning("mi_gestor_stock: no se pudo comprobar actualizaciones", exc_info=True)
            return ""
