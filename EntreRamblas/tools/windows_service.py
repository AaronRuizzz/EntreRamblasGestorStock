"""Servicio nativo Windows para Odoo. El registro requiere consola elevada."""
import argparse
import ctypes
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

import servicemanager
import win32service
import win32serviceutil
from service_process import OdooProcess


class StoreService(win32serviceutil.ServiceFramework):
    # Nombre interno del servicio (clave de compatibilidad, nunca cambiar);
    # el nombre mostrado en services.msc sí es el del producto visible.
    _svc_name_ = 'EntreRamblasOdoo'
    _svc_display_name_ = 'Gestor Stock Clavel Y Azahar'

    def __init__(self, args):
        super().__init__(args)
        self.stopping = threading.Event()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=120000)
        self.stopping.set()

    def SvcShutdown(self):
        self.SvcStop()

    def GetAcceptedControls(self):
        return super().GetAcceptedControls() | win32service.SERVICE_ACCEPT_PRESHUTDOWN

    def SvcOtherEx(self, control, event_type, data):
        if control == win32service.SERVICE_CONTROL_PRESHUTDOWN:
            self.SvcStop()
        else:
            return super().SvcOtherEx(control, event_type, data)

    def SvcDoRun(self):
        worker = OdooProcess(OPTIONS.config, OPTIONS.database, OPTIONS.git_executable)
        process = worker.start()
        try:
            while not self.stopping.wait(1):
                code = process.poll()
                if code is not None:
                    raise RuntimeError('Odoo terminó inesperadamente con código %s' % code)
            worker.request_stop()
            deadline = time.monotonic() + 100
            while process.poll() is None and time.monotonic() < deadline:
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=120000)
                time.sleep(1)
            if process.poll() is None:
                servicemanager.LogErrorMsg('Odoo no terminó en 100 segundos; se fuerza la parada. Revisar registros y copias.')
                process.kill()
                process.wait(timeout=10)
        finally:
            if process.poll() is None:
                worker.request_stop()
                try:
                    process.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            worker.close_output()


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'run', 'start', 'stop', 'remove', 'status'])
    parser.add_argument('--name', default='EntreRamblasOdoo')
    parser.add_argument('--config', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--postgres-service', help='Nombre exacto del servicio PostgreSQL')
    parser.add_argument('--git-executable', default=shutil.which('git'))
    OPTIONS = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', OPTIONS.name):
        raise ValueError('Nombre de servicio no válido')
    StoreService._svc_name_ = OPTIONS.name
    if OPTIONS.action == 'status':
        status = win32serviceutil.QueryServiceStatus(OPTIONS.name)
        labels = {win32service.SERVICE_STOPPED: 'Detenido', win32service.SERVICE_RUNNING: 'En ejecución',
                  win32service.SERVICE_START_PENDING: 'Arrancando', win32service.SERVICE_STOP_PENDING: 'Deteniéndose'}
        print(OPTIONS.name, labels.get(status[1], str(status[1])))
        return
    if OPTIONS.action == 'run':
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(StoreService)
        servicemanager.StartServiceCtrlDispatcher()
        return
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError('Abre PowerShell como administrador para registrar o controlar el servicio')
    if OPTIONS.action == 'install':
        # Git solo es necesario en un equipo de desarrollo (checkout de odoo/).
        # Una tienda instalada verifica la integridad por firma + hashes
        # (integridad.json), sin Git ni su historial.
        engine_uses_git = (Path(__file__).resolve().parents[1] / 'odoo' / '.git').exists()
        if engine_uses_git and not OPTIONS.git_executable:
            raise ValueError('No se encuentra Git; indica --git-executable')
        worker = OdooProcess(OPTIONS.config, OPTIONS.database, OPTIONS.git_executable)
        if not OPTIONS.postgres_service:
            raise ValueError('Indica --postgres-service con el nombre del servicio PostgreSQL')
        win32serviceutil.QueryServiceStatus(OPTIONS.postgres_service)
        try:
            win32serviceutil.QueryServiceStatus(OPTIONS.name)
        except Exception as error:
            if getattr(error, 'winerror', None) != 1060:
                raise
        else:
            raise ValueError('El servicio ya existe; no se reemplaza')
        # Servicio con privilegios limitados. Acceso solo al código y runtime elegidos.
        grants = [(Path(__file__).resolve().parents[1], 'RX'),
                  (Path(sys.base_prefix), 'RX'),
                  (worker.config.parent, 'M')]
        if engine_uses_git and OPTIONS.git_executable:
            git_directory = Path(OPTIONS.git_executable).resolve().parent
            if (git_directory.parent / 'mingw64').is_dir():
                git_directory = git_directory.parent
            grants.append((git_directory, 'RX'))
        for directory, access in grants:
            subprocess.run(['icacls', str(directory), '/grant', '*S-1-5-19:(OI)(CI)' + access], check=True)
        run_args = [str(Path(__file__).resolve()), 'run', '--name', OPTIONS.name,
                    '--config', str(worker.config), '--database', OPTIONS.database]
        if engine_uses_git and OPTIONS.git_executable:
            run_args += ['--git-executable', str(Path(OPTIONS.git_executable).resolve())]
        arguments = subprocess.list2cmdline(run_args)
        win32serviceutil.InstallService('windows_service.StoreService', OPTIONS.name, StoreService._svc_display_name_,
            startType=win32service.SERVICE_AUTO_START, delayedstart=True,
            serviceDeps=[OPTIONS.postgres_service], userName='NT AUTHORITY\\LocalService',
            exeName=sys.executable, exeArgs=arguments, description='Odoo local con parada ordenada y recuperación ante fallos.')
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        service = win32service.OpenService(scm, OPTIONS.name, win32service.SERVICE_CHANGE_CONFIG)
        try:
            win32service.ChangeServiceConfig2(service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
                {'ResetPeriod': 86400, 'RebootMsg': '', 'Command': '',
                 'Actions': [(win32service.SC_ACTION_RESTART, 120000), (win32service.SC_ACTION_RESTART, 180000),
                             (win32service.SC_ACTION_NONE, 0)]})
            win32service.ChangeServiceConfig2(service, win32service.SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, True)
            win32service.ChangeServiceConfig2(service, win32service.SERVICE_CONFIG_PRESHUTDOWN_INFO, 120000)
        finally:
            win32service.CloseServiceHandle(service)
            win32service.CloseServiceHandle(scm)
        print('Servicio instalado sin arrancarlo:', OPTIONS.name)
    elif OPTIONS.action == 'start':
        win32serviceutil.StartService(OPTIONS.name)
    elif OPTIONS.action == 'stop':
        win32serviceutil.StopService(OPTIONS.name)
    elif OPTIONS.action == 'remove':
        if win32serviceutil.QueryServiceStatus(OPTIONS.name)[1] != win32service.SERVICE_STOPPED:
            raise ValueError('Detén el servicio antes de retirarlo')
        win32serviceutil.RemoveService(OPTIONS.name)


if __name__ == '__main__':
    main()
