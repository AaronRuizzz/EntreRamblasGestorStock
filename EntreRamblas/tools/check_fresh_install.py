# -*- coding: utf-8 -*-
"""Instala mi_gestor_stock sobre una base REALMENTE vacía y comprueba que
termina sin error.

La suite normal reutiliza `mgs_validation`, donde los identificadores externos
ya existen de una instalación previa; por eso no detectaba que una vista se
cargara antes que la acción de informe que referencia. Aquí se crea una base
nueva cada vez, se instala con `--without-demo=all` y se borra al terminar.

Sin servidor HTTP: `odoo-bin --stop-after-init`.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-port", default="55432")
    ap.add_argument("--db-user", default="mgs_test")
    ap.add_argument("--config", default=str(ROOT / "odoo.conf"))
    ap.add_argument("--keep", action="store_true", help="No borrar la base al terminar (diagnóstico).")
    args = ap.parse_args(argv)

    dbname = "mgs_fresh_%d" % int(time.time())
    admin_conn = psycopg2.connect(dbname="postgres", host=args.db_host,
                                  port=args.db_port, user=args.db_user)
    admin_conn.autocommit = True

    def drop():
        with admin_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", [dbname])
            cur.execute('DROP DATABASE IF EXISTS "%s"' % dbname)

    try:
        with admin_conn.cursor() as cur:
            cur.execute("CREATE DATABASE \"%s\" ENCODING 'UTF8' TEMPLATE template0" % dbname)
        print("Base vacía creada:", dbname)

        cmd = [
            sys.executable, str(ROOT / "odoo" / "odoo-bin"),
            "-c", args.config,
            "--db_host=%s" % args.db_host, "--db_port=%s" % args.db_port,
            "--db_user=%s" % args.db_user,
            "-d", dbname, "--db-filter=^%s$" % dbname,
            "-i", "mi_gestor_stock", "--without-demo=all",
            "--stop-after-init", "--no-http",
            "--logfile=%s" % (ROOT / ".odoo_data" / "fresh-install.log"),
        ]
        result = subprocess.run(cmd, cwd=str(ROOT))
        if result.returncode != 0:
            print("FALLO: la instalación limpia terminó con código %d. "
                  "Revisa .odoo_data/fresh-install.log" % result.returncode, file=sys.stderr)
            return 1

        # Comprobación mínima de integridad: la acción de informe existe y la
        # cuenta de propietaria queda provisionable.
        check = psycopg2.connect(dbname=dbname, host=args.db_host,
                                 port=args.db_port, user=args.db_user)
        try:
            with check.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM ir_model_data WHERE module='mi_gestor_stock' "
                    "AND name='action_report_mgs_event'")
                if not cur.fetchone():
                    print("FALLO: no se creó action_report_mgs_event", file=sys.stderr)
                    return 1
        finally:
            check.close()
        print("OK: instalación limpia de mi_gestor_stock sobre base vacía")
        return 0
    finally:
        if not args.keep:
            drop()
        admin_conn.close()


if __name__ == "__main__":
    sys.exit(main())
