"""Odoo con canal privado de parada por stdin para el supervisor Windows."""
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'odoo'))
import odoo
import odoo.cli
import odoo.service.server


def stop_listener():
    # El pipe solo está abierto al supervisor que creó este proceso.
    # EOF también pide parar: evita dejar Odoo huérfano si cae el supervisor.
    command = sys.stdin.readline()
    if command.strip() not in ('', 'STOP'):
        return
    while odoo.service.server.server is None:
        time.sleep(0.1)
    # Ruta de apagado normal del ThreadedServer de la revisión Odoo fijada.
    # El bucle puede tardar hasta SLEEP_INTERVAL (60 s) en observarla.
    odoo.service.server.server.quit_signals_received = max(
        1, odoo.service.server.server.quit_signals_received)


if __name__ == '__main__':
    threading.Thread(target=stop_listener, name='mgs-stop', daemon=True).start()
    sys.argv[0] = str(ROOT / 'odoo/odoo-bin')
    odoo.cli.main()
