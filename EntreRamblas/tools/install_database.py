"""Operaciones del instalador sin contraseñas en argumentos ni SQL interpolado."""
import argparse
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'odoo'))
import odoo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['exists', 'reserve', 'provision'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', args.database):
        raise ValueError('Nombre de base no válido')
    odoo.tools.config.parse_config(['-c', args.config, '-d', args.database, '--no-http'])
    if args.operation == 'exists':
        with odoo.sql_db.db_connect('postgres').cursor() as cr:
            cr.execute('SELECT 1 FROM pg_database WHERE datname=%s', [args.database])
            print('exists' if cr.fetchone() else 'new')
        return
    pending = Path(args.config + '.pending')
    if not pending.is_file() or pending.read_text(encoding='utf-8').strip() != args.database:
        raise ValueError('Falta el marcador de instalación nueva; no se cambian credenciales existentes')
    if args.operation == 'reserve':
        from odoo.service import db as dbservice
        # CREATE DATABASE es atómico: otra instalación no puede reutilizar
        # accidentalmente un destino creado entre la comprobación y el inicio.
        dbservice._create_empty_database(args.database)
        print('Base vacía reservada para instalación:', args.database)
        return
    from odoo.modules.registry import Registry
    credentials = Path(args.config).parent / (args.database + '-first-access.secret')
    if credentials.exists():
        raise ValueError('Ya existe un archivo de acceso inicial; no se sobrescribe')
    password = secrets.token_urlsafe(24)
    with Registry(args.database).cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {'no_reset_password': True})
        module = env['ir.module.module'].search([('name', '=', 'mi_gestor_stock')], limit=1)
        if module.state != 'installed':
            raise ValueError('El módulo no se ha instalado correctamente')
        admin = env.ref('base.user_admin')
        admin.write({'login': 'propietaria', 'password': password, 'tz': 'Europe/Madrid'})
        # Sin datos fiscales reales no se habilitan tareas ni dispositivos por defecto.
        env['mgs.config']._mgs_get().write({'pos_autoprint': False})
        with credentials.open('x', encoding='utf-8') as stream:
            json.dump({'database': args.database, 'login': 'propietaria', 'password': password}, stream)
        cr.commit()
    pending.unlink()
    print('Acceso inicial guardado en', credentials)


if __name__ == '__main__':
    main()
