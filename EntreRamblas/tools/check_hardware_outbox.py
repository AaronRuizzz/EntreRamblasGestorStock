"""Prueba de transacciones reales, con transporte simulado y sin tocar hardware."""
import sys
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "odoo"))
import odoo
from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry

odoo.tools.config.parse_config([
    "-c", str(root / "odoo.conf"), "--db_host=127.0.0.1", "--db_port=55432",
    "--db_user=mgs_test", "-d", "mgs_validation", "--http-interface=127.0.0.1",
])
dbname = "mgs_validation"
reg = Registry(dbname)
from odoo.addons.mi_gestor_stock.models.mgs_hardware_job import dispatch_job

job_ids = []
sends = []


def transport(config, payload, doc_name="Ticket"):
    # El estado sending tiene que ser visible desde OTRA conexión antes del envío.
    with reg.cursor() as other:
        other.execute("SELECT state FROM mgs_hardware_job WHERE reason = %s", [doc_name])
        assert other.fetchone()[0] == "sending", "La intención no está confirmada antes del envío"
    sends.append(payload)
    if payload == b"uncertain":
        raise OSError("Simulación: conexión perdida después de escribir bytes")
    return True


try:
    with reg.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        config_type = type(env["mgs.config"])
    with patch.object(config_type, "_mgs_send", transport):
        for payload, expected in [(b"sent", "sent"), (b"uncertain", "uncertain")]:
            key = "smoke:%s" % uuid4()
            with reg.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                result = env["mgs.hardware.job"]._enqueue(key, "drawer", payload, key)
                job_ids.append(result["id"])
                cr.commit()  # Dispara el envío después de confirmar la solicitud.
            dispatch_job(dbname, result["id"])
            with reg.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                assert env["mgs.hardware.job"].browse(result["id"]).state == expected
                repeated = env["mgs.hardware.job"]._enqueue(key, "drawer", payload, key)
                assert repeated["existing"] and repeated["id"] == result["id"]
                cr.commit()
        assert sends == [b"sent", b"uncertain"], "Se ha repetido un envío"
        with reg.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            job = env["mgs.hardware.job"].create({
                "request_key": "smoke:%s" % uuid4(), "kind": "drawer", "state": "sending",
                "payload": "c3RvcA==", "reason": "Simulación reinicio", "user_id": SUPERUSER_ID,
                "company_id": env.company.id,
            })
            job_ids.append(job.id)
            cr.commit()
        dispatch_job(dbname, job.id)
        assert len(sends) == 2, "Se ha reenviado una operación interrumpida"
    print("OK: envío tras commit, reintentos idempotentes, resultado incierto y reinicio sin reenvío")
finally:
    # Solo se eliminan los registros creados por esta prueba, en la BD aislada.
    with reg.cursor() as cr:
        api.Environment(cr, SUPERUSER_ID, {})["mgs.hardware.job"].browse(job_ids).unlink()
        cr.commit()
