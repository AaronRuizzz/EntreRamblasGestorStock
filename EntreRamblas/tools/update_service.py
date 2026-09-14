# -*- coding: utf-8 -*-
r"""Servicio Windows «EntreRamblasActualizador»: el ÚNICO componente con
permisos para instalar una actualización (hallazgo 9 de la revisión
2026-09-10).

Por qué existe un segundo servicio, aparte del que sirve la app:

  * el servicio de la app (`EntreRamblasOdoo`) corre con la cuenta limitada
    LocalService: lectura/ejecución del código, sin escritura en Program
    Files. No puede reemplazar su propio código ni su venv mientras se
    ejecuta desde ahí (en Windows no se puede sustituir un .exe/.dll en uso).
  * este servicio corre con LocalSystem, arranque BAJO DEMANDA (nunca se
    inicia solo). Solo `mgs.update.action_accept()` lo arranca (`sc start`),
    y LocalService solo tiene permiso de ARRANCARLO (`sc sdset`, ver
    instalador\pasos-instalacion.ps1) — no de instalar ni reconfigurarlo.
  * usa el CPython VENDORIZADO (`<raíz>\python\python.exe`), no el venv de la
    app: así puede reconstruir/reemplazar ese venv sin bloquearse a sí mismo.
  * no se fía de `estado.json` (lo escribe el proceso menos privilegiado):
    `actualizador.py cmd_aplicar` re-verifica la firma, el hash y el
    consentimiento por sí mismo (ver `_reverify_staged_package`); este
    servicio es solo el que tiene permiso de invocarlo
    (`ENTRERAMBLAS_UPDATE_SERVICE=1`).

Uso (igual que windows_service.py):

    update_service.py install --config C --database D --postgres-service N
                              [--odoo-service EntreRamblasOdoo]
    update_service.py start | stop | status | remove
    update_service.py run          (interno; lo usa el SCM)

«Se instalará al cerrar», de verdad: al arrancar, intenta aplicar; si hay caja
abierta o ventas en curso, `actualizador.py` lo aplaza (código 4) y aquí se
reintenta cada pocos minutos hasta un tope de 12 horas, después de las cuales
se detiene dejando el estado en "preparado" con un mensaje claro.
"""
import argparse
import ctypes
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import servicemanager
import win32service
import win32serviceutil

ROOT = Path(__file__).resolve().parents[1]
ACTUALIZADOR = ROOT / "tools" / "actualizador.py"

RETRY_SECONDS = 5 * 60          # reintento si está aplazada (caja abierta, ...)
MAX_WAIT_SECONDS = 12 * 60 * 60  # tope: no reintenta indefinidamente


def _interpreter():
    """El CPython vendorizado si ya está instalado (toda actualización a
    partir de esta versión lo trae); si no (primera vez, versión anterior sin
    vendorizar), el mismo intérprete que corre este proceso."""
    vendored = ROOT / "python" / "python.exe"
    if vendored.is_file():
        return str(vendored)
    return sys.executable


class UpdateService(win32serviceutil.ServiceFramework):
    _svc_name_ = "EntreRamblasActualizador"
    _svc_display_name_ = "Entre Ramblas - Actualizador"

    def __init__(self, args):
        super().__init__(args)
        self.stopping = threading.Event()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=5000)
        self.stopping.set()

    def SvcShutdown(self):
        self.SvcStop()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("EntreRamblasActualizador: comprobando actualización pendiente.")
        try:
            self._apply_with_retries()
        except Exception as exc:  # noqa: BLE001 - se registra, el servicio igualmente se detiene
            servicemanager.LogErrorMsg("EntreRamblasActualizador: error inesperado: %s" % exc)
        servicemanager.LogInfoMsg("EntreRamblasActualizador: terminado; el servicio se detiene.")

    def _apply_with_retries(self):
        deadline = time.monotonic() + MAX_WAIT_SECONDS
        while not self.stopping.is_set():
            rc = _run_apply(OPTIONS.config, OPTIONS.database, OPTIONS.odoo_service)
            if rc == 4:  # aplazada: caja abierta / ventas en curso
                servicemanager.LogInfoMsg(
                    "EntreRamblasActualizador: aplazada (operación en curso); reintenta en %ds."
                    % RETRY_SECONDS)
                if time.monotonic() + RETRY_SECONDS > deadline:
                    servicemanager.LogWarningMsg(
                        "EntreRamblasActualizador: %dh sin poder aplicar; se detiene. "
                        "Vuelve a intentarlo cuando la tienda esté libre."
                        % (MAX_WAIT_SECONDS // 3600))
                    return
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                self.stopping.wait(RETRY_SECONDS)
                continue
            # 0 hecho, 1/6/7 no aplicable ahora, 5 fallo revertido: nada más
            # que reintentar automáticamente en esta ejecución del servicio.
            servicemanager.LogInfoMsg("EntreRamblasActualizador: terminado con código %s." % rc)
            return


def _run_apply(config, database, odoo_service):
    import os
    env = dict(os.environ, ENTRERAMBLAS_UPDATE_SERVICE="1")
    cmd = [_interpreter(), str(ACTUALIZADOR), "aplicar",
           "--config", config, "--database", database, "--destino", str(ROOT)]
    if odoo_service:
        cmd += ["--servicio", odoo_service]
    result = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return result.returncode


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "run", "start", "stop", "remove", "status"])
    parser.add_argument("--config")
    parser.add_argument("--database")
    parser.add_argument("--odoo-service", default="EntreRamblasOdoo")
    parser.add_argument("--postgres-service", help="Nombre del servicio PostgreSQL (dependencia)")
    OPTIONS = parser.parse_args()

    name = UpdateService._svc_name_
    if OPTIONS.action == "status":
        status = win32serviceutil.QueryServiceStatus(name)
        labels = {win32service.SERVICE_STOPPED: "Detenido", win32service.SERVICE_RUNNING: "En ejecución",
                  win32service.SERVICE_START_PENDING: "Arrancando", win32service.SERVICE_STOP_PENDING: "Deteniéndose"}
        print(name, labels.get(status[1], str(status[1])))
        return
    if OPTIONS.action == "run":
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(UpdateService)
        servicemanager.StartServiceCtrlDispatcher()
        return
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError("Abre PowerShell como administrador para registrar o controlar el servicio")
    if OPTIONS.action == "install":
        if not OPTIONS.config or not OPTIONS.database:
            raise ValueError("Indica --config y --database")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", OPTIONS.database):
            raise ValueError("Nombre de base no válido")
        try:
            win32serviceutil.QueryServiceStatus(name)
        except Exception as error:
            if getattr(error, "winerror", None) != 1060:
                raise
        else:
            raise ValueError("El servicio ya existe; no se reemplaza")
        deps = [OPTIONS.postgres_service] if OPTIONS.postgres_service else []
        arguments = subprocess.list2cmdline([
            str(Path(__file__).resolve()), "run",
            "--config", OPTIONS.config, "--database", OPTIONS.database,
            "--odoo-service", OPTIONS.odoo_service])
        win32serviceutil.InstallService(
            "update_service.UpdateService", name, UpdateService._svc_display_name_,
            startType=win32service.SERVICE_DEMAND_START,  # NUNCA arranca solo
            serviceDeps=deps, userName="LocalSystem",
            exeName=sys.executable, exeArgs=arguments,
            description="Aplica actualizaciones firmadas de Entre Ramblas. Arranque bajo demanda; "
                       "solo lo inicia la app al aceptar una actualización.")
        print("Servicio instalado (arranque bajo demanda):", name)
    elif OPTIONS.action == "start":
        win32serviceutil.StartService(name)
    elif OPTIONS.action == "stop":
        win32serviceutil.StopService(name)
    elif OPTIONS.action == "remove":
        if win32serviceutil.QueryServiceStatus(name)[1] != win32service.SERVICE_STOPPED:
            raise ValueError("Detén el servicio antes de retirarlo")
        win32serviceutil.RemoveService(name)


if __name__ == "__main__":
    main()
