"""Crea configuración privada y datos fuera de carpetas sincronizadas."""
import argparse
import configparser
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--source', help='Configuración privada existente para reutilizar conexión PostgreSQL')
    parser.add_argument('--db-host', default='127.0.0.1')
    parser.add_argument('--db-port', type=int, default=5432)
    parser.add_argument('--db-user', default='odoo')
    parser.add_argument('--http-port', type=int, default=8069)
    parser.add_argument('--pg-bin', help='Carpeta bin de PostgreSQL (psql y pg_dump)')
    parser.add_argument('--allow-existing', action='store_true',
                        help='El instalador ya reservo este directorio (logs, pgdata, '
                             'secretos). Salta SOLO la guarda de carpeta vacia; se '
                             'mantienen la de OneDrive/Dropbox, la de odoo.local ya '
                             'existente y el open(x) que nunca sobrescribe.')
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    for sync_root in [os.environ.get('OneDrive'), os.environ.get('OneDriveConsumer'), os.environ.get('OneDriveCommercial')]:
        if sync_root and directory.is_relative_to(Path(sync_root).resolve()):
            raise ValueError('Elige una carpeta fuera de OneDrive para datos y configuración')
    if any(part.lower().startswith(('onedrive', 'dropbox', 'google drive')) for part in directory.parts):
        raise ValueError('Elige una carpeta local sin sincronización')
    target = directory / 'odoo.local'
    if target.exists():
        raise ValueError('La configuración ya existe; no se sobrescribe')
    if not args.allow_existing and directory.exists() and any(directory.iterdir()):
        raise ValueError('Usa una carpeta nueva o vacía para preparar la instalación')
    config = configparser.ConfigParser(interpolation=None)
    if args.source:
        if not config.read(args.source, encoding='utf-8'):
            raise ValueError('No existe la configuración de origen')
    else:
        config['options'] = {}
        password = os.environ.get('MGS_DB_PASSWORD')
        if not password:
            raise ValueError('Indica MGS_DB_PASSWORD en el entorno o una configuración privada con --source')
        config['options']['db_password'] = password
    opts = config['options']
    opts.update({
        'addons_path': str(ROOT / 'odoo' / 'addons') + ',' + str(ROOT / 'custom_addons'),
        'db_host': args.db_host, 'db_port': str(args.db_port), 'db_user': args.db_user,
        'http_interface': '127.0.0.1', 'http_port': str(args.http_port),
        'list_db': 'False', 'admin_passwd': secrets.token_urlsafe(36),
        'data_dir': str(directory / 'data'), 'logfile': str(directory / 'odoo.log'),
        'log_level': 'info', 'workers': '0',
    })
    opts.pop('dev_mode', None)
    opts.pop('pg_path', None)
    if args.pg_bin:
        pg_bin = Path(args.pg_bin).resolve()
    else:
        pg_root = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'PostgreSQL'
        candidates = sorted([p for p in pg_root.glob('*/bin') if p.parent.name.isdigit()],
                            key=lambda p: int(p.parent.name), reverse=True)
        pg_bin = candidates[0] if candidates else None
    if not pg_bin or not all((pg_bin / (name + '.exe')).is_file() for name in ['psql', 'pg_dump']):
        raise ValueError('Indica --pg-bin con la carpeta bin de PostgreSQL')
    opts['pg_path'] = str(pg_bin)
    opts.pop('dbfilter', None)
    preexisting = directory.exists() and any(directory.iterdir())
    directory.mkdir(parents=True, exist_ok=True)
    # No reescribir las ACL de un directorio que el instalador ya preparo (puede
    # contener el cluster PostgreSQL en marcha): '/inheritance:r' sobre esa
    # carpeta romperia el acceso del servicio. El instalador fija los permisos
    # en la seccion [Dirs] de EntreRamblas-Setup.iss.
    if os.name == 'nt' and not (args.allow_existing and preexisting):
        identity = os.environ['USERDOMAIN'] + '\\' + os.environ['USERNAME']
        subprocess.run(['icacls', str(directory), '/inheritance:r', '/grant:r',
                        identity + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    with target.open('x', encoding='utf-8') as stream:
        config.write(stream)
    print(target)


if __name__ == '__main__':
    main()
