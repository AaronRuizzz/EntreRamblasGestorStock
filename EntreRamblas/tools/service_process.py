"""Supervisor independiente del SCM: mismo código para servicio y pruebas."""
import configparser
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


class OdooProcess:
    def __init__(self, config, database, git_executable='git', cron_threads=None):
        self.config = Path(config).resolve(strict=True)
        self.database = database
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', database):
            raise ValueError('Nombre de base no válido')
        if Path(str(self.config) + '.pending').exists():
            raise ValueError('La instalación está incompleta')
        # Integridad del código: en desarrollo compara el commit de Git; en una
        # tienda instalada (sin Git) verifica la firma y los hashes de
        # integridad.json. Mismo criterio que el arranque manual.
        sys.path.insert(0, str(ROOT / 'tools'))
        import verificar_motor
        report = verificar_motor.check()
        if report.get('code') == 4:
            raise ValueError('No se pudo verificar la integridad del código: %s'
                             % report.get('detalle', report.get('estado')))
        if report.get('code') != 0:
            raise ValueError('La revisión Odoo no coincide con el proyecto (%s)'
                             % report.get('estado'))
        settings = configparser.ConfigParser(interpolation=None)
        settings.read(self.config, encoding='utf-8')
        options = settings['options']
        if options.get('dev_mode', '').strip():
            raise ValueError('El servicio requiere dev_mode desactivado')
        if options.get('http_interface') != '127.0.0.1':
            raise ValueError('El servicio de tienda requiere escucha en 127.0.0.1')
        if options.getint('workers', 0) != 0:
            raise ValueError('El servicio Windows requiere workers = 0')
        self.process = None
        self.output = None
        self.cron_threads = cron_threads

    def start(self):
        environment = os.environ.copy()
        # wkhtmltopdf: junto a la configuración (instalación manual) o el que
        # viaja en el paquete bajo tools/wkhtmltox (instalación de la tienda).
        for wk in (self.config.parent / 'tools/wkhtmltox/bin', ROOT / 'tools/wkhtmltox/bin'):
            if (wk / 'wkhtmltopdf.exe').is_file():
                environment['PATH'] = str(wk) + os.pathsep + environment['PATH']
                break
        self.output = (self.config.parent / 'service-process.log').open('ab')
        try:
            command = [
                sys.executable, str(ROOT / 'tools/service_worker.py'), '-c', str(self.config),
                '-d', self.database, '--db-filter=^' + self.database + '$',
            ]
            if self.cron_threads is not None:
                command.append('--max-cron-threads=' + str(self.cron_threads))
            self.process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.PIPE,
                stdout=self.output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except Exception:
            self.output.close()
            raise
        return self.process

    def request_stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.stdin.write(b'STOP\n')
                self.process.stdin.flush()
                self.process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass

    def close_output(self):
        if self.output:
            self.output.close()
