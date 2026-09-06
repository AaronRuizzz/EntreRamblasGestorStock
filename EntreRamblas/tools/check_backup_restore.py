"""Copia y restauración reales, exclusivamente en PostgreSQL aislado de pruebas."""
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "odoo"))
import odoo
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.service import db as dbservice
from restore_backup import restore_archive

odoo.tools.config.parse_config([
    "-c", str(root / "odoo.conf"), "--db_host=127.0.0.1", "--db_port=55432",
    "--db_user=mgs_test", "-d", "mgs_validation",
])
odoo.tools.config["list_db"] = True
reg = Registry("mgs_validation")
restored = "mgs_restore_test_" + uuid4().hex[:12]
directory = root / ".odoo_data" / "backup-validation"
ssd = directory / "simulated-ssd"
ssd.mkdir(parents=True, exist_ok=True)
payload = b"Adjunto de prueba para comprobar la recuperacion del filestore"
attachment_id = None
try:
    with reg.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        attachment = env["ir.attachment"].create({"name": "backup-probe.txt", "raw": payload})
        attachment_id = attachment.id
        cr.commit()
    with reg.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        config = env["mgs.config"]._mgs_get()
        config.write({"backup_dir": str(directory), "backup_ssd_dir": str(ssd)})
        backup = env["mgs.backup"]._mgs_run_backup("manual")
        assert backup.state == "done", backup.message
        assert backup.replica_state == "done", backup.message
        archive_path = backup.path
        assert backup.checksum == hashlib.sha256(Path(backup.replica_path).read_bytes()).hexdigest()
        counts = {}
        for model in ["product.product", "pos.order", "stock.move.line", "stock.lot"]:
            counts[model] = env[model].search_count([])
        # No persiste la configuración temporal ni el registro de la prueba.
    restore_archive(archive_path, restored)
    with Registry(restored).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        for model, count in counts.items():
            assert env[model].search_count([]) == count, model
        assert env["ir.attachment"].browse(attachment_id).raw == payload
    print("OK: ZIP completo, SHA-256, replica SSD simulada, restauracion SQL y adjuntos")
    print("Copia de evidencia:", archive_path)
finally:
    # Solo elimina la base temporal cuyo nombre se acaba de generar, nunca la fuente.
    assert restored.startswith("mgs_restore_test_") and restored != "mgs_validation"
    filestore_root = Path(odoo.tools.config["data_dir"]).resolve() / "filestore"
    assert Path(odoo.tools.config.filestore(restored)).resolve().parent == filestore_root
    if dbservice.exp_db_exist(restored):
        dbservice.exp_drop(restored)
    if attachment_id:
        with reg.cursor() as cr:
            api.Environment(cr, SUPERUSER_ID, {})["ir.attachment"].browse(attachment_id).unlink()
            cr.commit()
