"""Operaciones del instalador sin contraseñas en argumentos ni SQL interpolado."""
import argparse
from pathlib import Path
import re
# secrets ya no se usa aquí: la provisión vive en mgs.access._mgs_provision_owner
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
    activation_file = Path(args.config).parent / (args.database + '-activacion.txt')
    if activation_file.exists():
        raise ValueError('Ya existe un archivo de activación; no se sobrescribe')
    with Registry(args.database).cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {'no_reset_password': True})
        module = env['ir.module.module'].search([('name', '=', 'mi_gestor_stock')], limit=1)
        if module.state != 'installed':
            raise ValueError('El módulo no se ha instalado correctamente')
        # La caja de la tienda se crea durante la instalación; si falta, algo
        # falló al preparar la contabilidad o el TPV. No dejar la instalación
        # como terminada: se conserva el marcador .pending para poder reanudar.
        if not env.ref('mi_gestor_stock.pos_config_shop', raise_if_not_found=False):
            raise ValueError(
                'La caja de la tienda no se creó (revisa el plan contable en el '
                'registro). Se conserva el marcador pendiente; corrige y repite.')
        # Provisión única de la propietaria (mismo código que la migración):
        # cuenta separada con permisos de gestión de tienda, `admin` queda solo
        # como cuenta técnica de rotura de cristal SIN contraseña utilizable, y
        # el primer acceso queda pendiente de un código de activación de un
        # solo uso. Ver models/mgs_access.py:_mgs_provision_owner.
        code = env['mgs.access']._mgs_provision_owner(neutralize_admin=True)
        if not code:
            raise ValueError('La cuenta de propietaria ya estaba provisionada; '
                             'no se genera un código de activación nuevo')
        # Sin datos fiscales reales no se habilitan tareas ni dispositivos por defecto.
        env['mgs.config']._mgs_get().write({'pos_autoprint': False})
        with activation_file.open('x', encoding='utf-8') as stream:
            stream.write(
                'Codigo de activacion para el primer acceso de la propietaria\n'
                'Base de datos: ' + args.database + '\n\n'
                '    ' + code + '\n\n'
                'Abre el programa. En la pantalla de primer acceso escribe este\n'
                'codigo y elige una contrasena de 12+ caracteres. Guarda despues\n'
                'la clave de recuperacion que te muestre. Borra este archivo\n'
                'cuando termines.\n')
        cr.commit()
    pending.unlink()
    print('Codigo de activacion del primer acceso guardado en', activation_file)


if __name__ == '__main__':
    main()
