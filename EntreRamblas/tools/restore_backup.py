"""Restaura una copia verificada en una base NUEVA, conservando la original."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "odoo"))
import odoo
from backup_archive import validate_archive


def restore_archive(filename, database, allow_legacy=False):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database):
        raise ValueError("Nombre de base inválido: usa letras minúsculas, números y guion bajo")
    manifest = validate_archive(filename, allow_legacy)
    from odoo.service import db as dbservice
    from odoo.tools.misc import exec_pg_environ, find_pg_tool
    from odoo.modules.registry import Registry
    odoo.tools.config["list_db"] = True
    if dbservice.exp_db_exist(database):
        raise ValueError("La base destino ya existe. Elige otro nombre; se conserva la base original")
    target = Path(odoo.tools.config.filestore(database)).resolve()
    filestore_root = Path(odoo.tools.config["data_dir"]).resolve() / "filestore"
    if target.parent != filestore_root or target.exists():
        raise ValueError("El destino del filestore no es nuevo o no está dentro de la carpeta prevista")
    dbservice._create_empty_database(database)
    with tempfile.TemporaryDirectory(prefix="mgs-restore-") as folder:
        with zipfile.ZipFile(filename) as archive:
            archive.extractall(folder)
        # Sin ON_ERROR_STOP psql puede ocultar errores y aparentar éxito.
        subprocess.run([find_pg_tool("psql"), "--dbname=" + database, "--set=ON_ERROR_STOP=1",
                        "--single-transaction", "-q", "-f", str(Path(folder) / "dump.sql")],
                       env=exec_pg_environ(), stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, check=True, timeout=1800)
        source = Path(folder) / "filestore"
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
    with Registry.new(database).cursor() as cr:
        env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
        env["ir.config_parameter"].init(force=True)
        env["ir.cron"].search([]).write({"active": False})
        config = env["mgs.config"]._mgs_get()
        config.write({"backup_enabled": False, "pos_autoprint": False})
        env["mgs.hardware.job"].search([("state", "in", ["pending", "sending"])]).write({
            "state": "uncertain", "message": "Recuperada desde copia: comprobar resultado antes de repetir"})
        cr.commit()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archivo")
    parser.add_argument("-c", "--config", default=str(PROJECT / "odoo.conf"))
    parser.add_argument("-d", "--database", required=True, help="Nombre NUEVO para la base recuperada")
    parser.add_argument("--allow-legacy", action="store_true", help="Aceptar copia antigua sin SHA-256")
    args = parser.parse_args()
    odoo.tools.config.parse_config(["-c", args.config])
    restore_archive(str(Path(args.archivo).resolve()), args.database, args.allow_legacy)
    print("Restauración completada en", args.database)
    print("Antes del uso: comprobar datos y dispositivos, configurar copias y reactivar tareas automáticas.")


if __name__ == "__main__":
    main()
