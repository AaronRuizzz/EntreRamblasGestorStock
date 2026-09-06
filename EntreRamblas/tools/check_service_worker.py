"""Ensaya el mismo supervisor y proceso Odoo sin registrar un servicio Windows."""
import os
from pathlib import Path
import socket
import time
import urllib.request

from service_process import OdooProcess

config = Path(os.environ['LOCALAPPDATA']) / 'EntreRamblasValidation/config-permissions-20260905/odoo.local'
worker = OdooProcess(config, 'mgs_install_validation_v2', cron_threads=0)
process = worker.start()
try:
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError('El proceso terminó durante el arranque')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8077/web/login', timeout=2) as response:
                assert response.status == 200
                break
        except OSError:
            time.sleep(0.5)
    else:
        raise AssertionError('No respondió el servidor de prueba')
    print('OK: Odoo responde en 8077 mediante el supervisor de servicio', flush=True)
    worker.request_stop()
    assert process.wait(timeout=100) == 0, 'La parada no fue limpia'
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', 8077)) != 0, 'El puerto sigue ocupado'
    print('OK: parada ordenada por canal privado, código 0 y puerto liberado', flush=True)
finally:
    if process.poll() is None:
        process.kill()
        process.wait(timeout=10)
    worker.close_output()
