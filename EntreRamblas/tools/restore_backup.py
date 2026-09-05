# -*- coding: utf-8 -*-
"""Restaura una copia de seguridad .zip creada por el Gestor de Stock.

Se ejecuta con el SERVIDOR PARADO (no se puede restaurar una base de datos
que esta en uso). Lo normal es lanzarlo desde restore-backup.ps1, que ya
comprueba que el puerto 8069 este libre.

    venv\\Scripts\\python.exe tools\\restore_backup.py copia.zip -d mi_base_stock

El .zip lleva dentro dump.sql + filestore/ + manifest.json, que es el formato
nativo de Odoo: tambien se puede restaurar desde el gestor de bases de datos
de cualquier Odoo 18.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
# El codigo fuente de Odoo vive en EntreRamblas\odoo\ (ver README §3).
sys.path.insert(0, os.path.join(PROJECT, "odoo"))

import odoo  # noqa: E402 - despues de tocar sys.path


def main():
    parser = argparse.ArgumentParser(description="Restaura una copia del Gestor de Stock.")
    parser.add_argument("archivo", help="Ruta del .zip de la copia")
    parser.add_argument("-c", "--config", default=os.path.join(PROJECT, "odoo.conf"))
    parser.add_argument("-d", "--database", default="mi_base_stock")
    parser.add_argument("--force", action="store_true",
                        help="Borra la base de datos actual antes de restaurar")
    args = parser.parse_args()

    archivo = os.path.abspath(args.archivo)
    if not os.path.isfile(archivo):
        sys.exit("No existe el archivo: %s" % archivo)

    odoo.tools.config.parse_config(["-c", args.config])
    # dump_db / restore_db / exp_drop llevan el decorador
    # check_db_management_enabled, que las bloquea cuando list_db = False
    # (asi esta odoo.conf, para ocultar el gestor de BD en el navegador).
    # Aqui, en local y con el servidor parado, se levanta a proposito.
    odoo.tools.config["list_db"] = True

    from odoo.service import db as dbservice  # noqa: PLC0415 - tras parse_config

    if dbservice.exp_db_exist(args.database):
        if not args.force:
            sys.exit(
                "La base de datos '%s' ya existe.\n"
                "Vuelve a lanzarlo con --force para reemplazarla "
                "(se pierde todo lo que no este en la copia)." % args.database)
        print("Borrando la base de datos '%s'..." % args.database)
        dbservice.exp_drop(args.database)

    print("Restaurando '%s' desde %s ..." % (args.database, archivo))
    dbservice.restore_db(args.database, archivo, copy=False)
    print("Listo. Arranca el servidor con  .\\start-odoo.ps1")


if __name__ == "__main__":
    main()
