# -*- coding: utf-8 -*-
"""Genera el informe mensual en PDF con wkhtmltopdf, con los permisos REALES de
la aplicación (la cuenta de la propietaria, no superusuario) y contra la base
que se le indique.

Antes estaba cableado al cluster de pruebas (55432 / mgs_test / mgs_validation /
8075) y a superusuario, así que en una instalación real siempre fallaba y el
instalador lo degradaba a un aviso. Ahora se parametriza y devuelve un código de
salida propio (0 correcto, 1 fallo).

Requiere el servidor HTTP en marcha (wkhtmltopdf descarga de ahí los estilos):
en el instalador ya lo está cuando se llega a este paso.
"""
import argparse
import configparser
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _http_base_from_config(config_path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_path, encoding="utf-8")
    opts = parser["options"] if parser.has_section("options") else {}
    host = opts.get("http_interface") or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    port = opts.get("http_port") or "8069"
    return "http://%s:%s" % (host, port)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(ROOT / "odoo.conf"))
    ap.add_argument("--database", required=True)
    ap.add_argument("--db-host", default=None)
    ap.add_argument("--db-port", default=None)
    ap.add_argument("--db-user", default=None)
    ap.add_argument("--report-url", default=None,
                    help="Base HTTP que ve wkhtmltopdf; por defecto se deriva de la config.")
    ap.add_argument("--wkhtmltopdf-bin", default=None,
                    help="Carpeta bin con wkhtmltopdf.exe. Por defecto <config>/tools/wkhtmltox/bin.")
    ap.add_argument("--salida", default=str(ROOT / ".odoo_data/output/pdf/informe-validacion.pdf"))
    args = ap.parse_args(argv)

    config_dir = Path(args.config).resolve().parent
    wk_bin = Path(args.wkhtmltopdf_bin) if args.wkhtmltopdf_bin else config_dir / "tools" / "wkhtmltox" / "bin"
    if wk_bin.is_dir():
        os.environ["PATH"] = str(wk_bin) + os.pathsep + os.environ.get("PATH", "")

    sys.path.insert(0, str(ROOT / "odoo"))
    import odoo
    from odoo import api, SUPERUSER_ID
    from odoo.modules.registry import Registry

    parse_args = ["-c", args.config, "-d", args.database, "--no-http"]
    for flag, value in (("--db_host", args.db_host), ("--db_port", args.db_port),
                        ("--db_user", args.db_user)):
        if value:
            parse_args.append("%s=%s" % (flag, value))
    odoo.tools.config.parse_config(parse_args)

    report_url = args.report_url or _http_base_from_config(args.config)

    rc = 1
    with Registry(args.database).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {"lang": "es_ES", "tz": "Europe/Madrid"})
        params = env["ir.config_parameter"]
        previous = params.get_param("report.url")
        params.set_param("report.url", report_url)

        owner = env["res.users"]._mgs_owner()
        if not owner:
            env["mgs.access"]._mgs_provision_owner()
            owner = env["res.users"]._mgs_owner()
        run_as = owner or env["res.users"].browse(SUPERUSER_ID)
        report = env["mgs.monthly.report"].with_user(run_as).create({})
        cr.commit()
        try:
            pdf, kind = env["ir.actions.report"].with_user(run_as)._render_qweb_pdf(
                "mi_gestor_stock.action_report_mgs_monthly", [report.id])
            if kind != "pdf" or not pdf.startswith(b"%PDF-"):
                print("ERROR: no se ha generado un PDF real (kind=%r)" % kind, file=sys.stderr)
            else:
                target = Path(args.salida)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(pdf)
                print("PDF generado como %s: %s" % (run_as.login, target))
                rc = 0
        except Exception as exc:  # noqa: BLE001 - lo reportamos por código de salida
            print("ERROR al generar el PDF: %s" % exc, file=sys.stderr)
        finally:
            params.set_param("report.url", previous or False)
            report.unlink()
            cr.commit()
    return rc


if __name__ == "__main__":
    sys.exit(main())
