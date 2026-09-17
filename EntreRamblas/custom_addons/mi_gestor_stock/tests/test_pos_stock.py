from datetime import datetime, timedelta
import base64
import csv
import io
import re
import zipfile
from uuid import uuid4
from unittest.mock import patch

import pytz

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged, new_test_user
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestPosStock(TestPointOfSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.report_category = cls.env["product.category"].create({"name": "Prueba coste TPV"})
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa TPV", "tracking": "lot", "mgs_auto_lots": True,
            "categ_id": cls.report_category.id,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})

    def receive(self, quantity, cost, days):
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.flower.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def test_close_marks_backup_pending_until_success(self):
        config = self.env["mgs.config"]._mgs_get()
        config.backup_enabled = True
        self.session.action_pos_session_close()
        self.assertEqual(self.session.state, "closed")
        self.assertTrue(self.session.mgs_backup_pending)
        model = self.env["mgs.backup"]
        failed = model.create({"state": "error", "message": "Disco lleno"})
        with patch.object(type(model), "_mgs_run_backup", return_value=failed):
            model._mgs_backup_closed_sessions()
        self.assertTrue(self.session.mgs_backup_pending)
        success = model.create({"state": "done"})
        with patch.object(type(model), "_mgs_run_backup", return_value=success):
            model._mgs_backup_closed_sessions()
        self.assertFalse(self.session.mgs_backup_pending)

    def order(self, quantity, original=False):
        return self.env["pos.order"].create({
            "uuid": str(uuid4()),
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": quantity * 10, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.flower.id, "qty": quantity, "price_unit": 10,
                "price_subtotal": quantity * 10, "price_subtotal_incl": quantity * 10,
                "refunded_orderline_id": original.id if original else False,
            })],
        })

    def test_owner_without_email_can_open_the_register(self):
        # Revisión 2026-09-10, hallazgo 17: con la propietaria y la empresa sin
        # correo, «Abrir caja registradora» abortaba porque publicar un mensaje
        # como la propietaria (no superusuario) exige un remitente.
        self.env["res.users"].sudo().search(
            [("mgs_is_owner", "=", True)]).write({"mgs_is_owner": False})
        owner = new_test_user(
            self.env, login="mgs_owner_sin_correo",
            groups="mi_gestor_stock.group_mgs_manager")
        owner.mgs_is_owner = True
        owner.partner_id.email = False
        self.env.company.partner_id.email = False
        self.env.company.write({"email": False})
        # self.session (de setUpClass) ya ocupa self.pos_config en
        # opening_control: crear una segunda sesión para la misma caja
        # violaría "Ya hay otra sesión abierta para este punto de venta".
        self.session.with_user(owner).set_opening_control(0, "")
        self.assertEqual(self.session.state, "opened")

    def test_pos_sale_and_partial_refunds(self):
        first = self.receive(5, 2, 3)
        second = self.receive(10, 4, 8)
        order = self.order(7)
        order._create_order_picking()
        self.assertEqual(order.picking_ids.state, "done")
        self.assertEqual(self.flower.qty_available, 8)
        order._create_order_picking()
        self.assertEqual(self.flower.qty_available, 8)
        self.flower.standard_price = 99
        refund = self.order(-3, order.lines)
        refund._create_order_picking()
        self.assertEqual(refund.picking_ids.state, "done")
        self.assertEqual(refund.picking_ids.move_line_ids.lot_id, first)
        self.assertEqual(refund.picking_ids.move_line_ids.mgs_unit_cost, 2)
        second_refund = self.order(-4, order.lines)
        second_refund._create_order_picking()
        lines = second_refund.picking_ids.move_line_ids
        self.assertEqual(set(lines.lot_id.ids), {first.id, second.id})
        self.assertEqual(sum(line.quantity * line.mgs_unit_cost for line in lines), 12)
        self.assertEqual(self.flower.qty_available, 15)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.order(-1, order.lines)._create_order_picking()

    def test_pos_rejects_stock_shortage_and_unlinked_refund(self):
        self.receive(2, 2, 3)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.order(3)._create_order_picking()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.order(-1)._create_order_picking()
        self.assertEqual(self.flower.qty_available, 2)

    def test_damaged_refund_scraps_original_lots_once(self):
        self.receive(2, 2, 3)
        self.receive(3, 4, 8)
        sale = self.order(4)
        sale._create_order_picking()
        self.flower.standard_price = 99
        refund = self.order(-3, sale.lines)
        refund.lines.mgs_damaged_return = True
        refund._create_order_picking()
        refund.lines._compute_total_cost(refund.picking_ids.move_ids)
        self.assertEqual(self.flower.qty_available, 1)
        self.assertEqual(refund.lines.total_cost, -8)
        scraps = self.env['stock.scrap'].search([('mgs_return_line_id', 'in', refund.picking_ids.move_line_ids.ids)])
        self.assertEqual(len(scraps), 2)
        self.assertEqual(set(scraps.mapped('state')), {'done'})
        self.assertEqual(set(scraps.mapped('mgs_reason')), {'return'})
        self.assertEqual(sum(ml.quantity_product_uom * ml.mgs_unit_cost for ml in scraps.move_ids.move_line_ids), 8)
        refund._create_order_picking()
        self.assertEqual(self.flower.qty_available, 1)
        self.assertEqual(self.env['stock.scrap'].search_count([('mgs_return_line_id', 'in', refund.picking_ids.move_line_ids.ids)]), 2)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            refund.lines.mgs_damaged_return = False
        recovered = self.order(-1, sale.lines)
        recovered._create_order_picking()
        self.assertEqual(self.flower.qty_available, 2)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.order(-1, sale.lines)._create_order_picking()

    def test_damaged_refund_failure_rolls_back_return(self):
        self.receive(2, 2, 3)
        sale = self.order(2)
        sale._create_order_picking()
        refund = self.order(-1, sale.lines)
        refund.lines.mgs_damaged_return = True
        with self.assertRaises(UserError), self.env.cr.savepoint():
            with patch.object(type(self.env['stock.scrap']), 'do_scrap', side_effect=UserError('Fallo de merma')):
                refund._create_order_picking()
        self.assertEqual(self.flower.qty_available, 0)
        self.assertFalse(refund.picking_ids)
        refund._create_order_picking()
        self.assertEqual(self.flower.qty_available, 0)

    def test_staff_damaged_untracked_return_preserves_cost(self):
        self.flower.write({'tracking': 'none', 'mgs_auto_lots': False, 'standard_price': 2})
        location = self.pos_config.picking_type_id.default_location_src_id
        self.env['stock.quant']._update_available_quantity(self.flower, location, 2)
        sale = self.order(1)
        sale._create_order_picking()
        self.flower.standard_price = 99
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login='mgs_damaged_staff', groups='mi_gestor_stock.group_mgs_user', company_id=self.env.company.id)
        refund = self.order(-1, sale.lines)
        refund.lines.mgs_damaged_return = True
        refund.with_user(staff)._create_order_picking()
        scrap = self.env['stock.scrap'].search([('mgs_return_line_id', 'in', refund.picking_ids.move_line_ids.ids)])
        self.assertEqual(self.flower.qty_available, 1)
        self.assertEqual(scrap.move_ids.move_line_ids.mgs_unit_cost, 2)
        self.assertEqual(scrap.mgs_validated_by, staff)

    def test_report_uses_historical_cost_after_price_change_and_refund(self):
        self.receive(5, 2, 3)
        self.receive(10, 4, 8)
        order = self.order(7)
        order._create_order_picking()
        order.lines._compute_total_cost(order.picking_ids.move_ids)
        order.state = "paid"
        self.assertEqual(order.lines.total_cost, 18)
        self.flower.standard_price = 99
        refund = self.order(-3, order.lines)
        refund._create_order_picking()
        refund.lines._compute_total_cost(refund.picking_ids.move_ids)
        refund.state = "paid"
        # Día de Madrid, no de UTC (ver mgs_monthly_report._mgs_period): cerca
        # de la medianoche española un pedido fechado "ahora mismo" quedaría
        # fuera de la ventana del informe si aquí se usara fields.Date.today().
        today = datetime.now(pytz.timezone("Europe/Madrid")).date()
        report = self.env["mgs.monthly.report"].create({
            "date_from": today, "date_to": today,
            "category_id": self.report_category.id,
        })
        data = report.mgs_get_report_data()
        self.assertEqual(data["total_revenue"], 40)
        self.assertEqual(data["total_cost_sold"], 12)
        self.assertEqual(data["gross_profit"], 28)
        self.assertEqual(data["purchases"], 50)
        self.assertEqual(data["stock_value"], 38)
        self.assertEqual(data["missing_costs"], 0)
        self.assertEqual(data["sale_ticket_count"], 1)
        self.assertEqual(data["refund_ticket_count"], 1)
        self.assertEqual(data["average_sale_ticket"], 70)
        self.assertEqual(data["refunds_including_tax"], 30)
        self.assertFalse(data["payments_available"])
        self.assertEqual(sum(row["revenue"] for row in data["daily_rows"]), 40)
        scrap = self.env["stock.scrap"].create({"product_id": self.flower.id,
            "lot_id": refund.picking_ids.move_line_ids.lot_id.id, "scrap_qty": 1,
            "location_id": self.pos_config.picking_type_id.default_location_src_id.id,
            "mgs_reason": "deterioration"})
        scrap.do_scrap()
        data = report.mgs_get_report_data()
        self.assertEqual(data["scrap_cost"], 2)
        self.assertEqual(data["margin_after_scrap"], 26)
        self.assertEqual(data["stock_value"], 36)
        report.action_export_csv()
        self.assertIn("Rosa TPV", base64.b64decode(report.csv_file).decode("utf-8-sig"))
        self.flower.name = '  =HYPERLINK("https://example.invalid")'
        report.action_export_all_csv()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(report.export_file))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertNotIn('cobros.csv', archive.namelist())
            def rows(name):
                return list(csv.reader(io.StringIO(archive.read(name).decode('utf-8-sig')), delimiter=';'))
            summary = dict(rows('resumen.csv')[1:])
            self.assertEqual(float(summary['Margen después de mermas']), 26)
            self.assertEqual(float(summary['Valor de stock actual']), 36)
            self.assertTrue(rows('ventas.csv')[1][0].startswith("'  ="))
            self.assertEqual(float(rows('ventas_diarias.csv')[1][1]), 40)
            self.assertEqual(float(rows('mermas.csv')[1][-1]), 2)
            self.assertEqual(float(rows('stock_actual.csv')[1][-1]), 36)
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            "mi_gestor_stock.report_mgs_monthly_document", [report.id])
        self.assertIn(b"Margen bruto", html)

    def test_report_period_madrid_includes_entire_local_day(self):
        report = self.env["mgs.monthly.report"].create({"date_from": "2026-03-29", "date_to": "2026-03-29"})
        start, end = report._mgs_period()
        self.assertEqual(str(start), "2026-03-28 23:00:00")
        self.assertEqual(str(end), "2026-03-29 22:00:00")
        report.date_to = "2026-03-28"
        with self.assertRaises(UserError):
            report.mgs_get_report_data()

    def test_report_payments_use_payment_date_and_net_change(self):
        order = self.order(1)
        order.write({"state": "paid", "date_order": "2080-06-01 10:00:00"})
        for method, amount in [(self.cash_payment_method, 8), (self.bank_payment_method, 4),
                               (self.cash_payment_method, -2)]:
            self.env["pos.payment"].create({"pos_order_id": order.id,
                "payment_method_id": method.id, "amount": amount,
                "payment_date": "2080-06-02 10:00:00"})
        credit = self.order(1)
        credit.write({"state": "paid", "date_order": "2080-06-01 10:00:00"})
        self.env["pos.payment"].create({"pos_order_id": credit.id,
            "payment_method_id": self.credit_payment_method.id, "amount": 10,
            "payment_date": "2080-06-02 10:00:00"})
        report = self.env["mgs.monthly.report"].create({"date_from": "2080-06-02", "date_to": "2080-06-02"})
        data = report.mgs_get_report_data()
        self.assertEqual(data["total_revenue"], 0)
        self.assertEqual(data["payments_net"], 10)
        self.assertEqual(data["payments_deferred_net"], 10)
        self.assertEqual(sum(row["returned"] for row in data["payment_rows"]), 2)
        self.assertEqual(data["average_sale_ticket"], 0)
        report.action_export_all_csv()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(report.export_file))) as archive:
            rows = list(csv.DictReader(io.StringIO(archive.read('cobros.csv').decode('utf-8-sig')), delimiter=';'))
            self.assertEqual(sum(float(r['Neto']) for r in rows if r['Cuenta cliente no cobrada'] == 'No'), 10)
            self.assertEqual(sum(float(r['Neto']) for r in rows if r['Cuenta cliente no cobrada'] == 'Sí'), 10)

    def test_staff_can_sell_and_scrap_without_receiving_costs(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)), login="mgs_pos_staff", groups="mi_gestor_stock.group_mgs_user",
                              company_id=self.env.company.id)
        lot = self.receive(5, 3, 5)
        order = self.order(2).with_user(staff)
        order._create_order_picking()
        order._compute_total_cost_in_real_time()
        self.assertEqual(order.picking_ids.state, "done")
        self.assertEqual(order.lines.sudo().total_cost, 6)
        scrap = self.env["stock.scrap"].with_user(staff).create({
            "product_id": self.flower.id, "lot_id": lot.id, "scrap_qty": 1,
        })
        scrap.do_scrap()
        self.assertEqual(self.flower.qty_available, 2)
        self.assertEqual(scrap.mgs_validated_by, staff)

    def test_stock_precheck_aggregates_lines_and_recovers_confirmed_order(self):
        self.session.state = "opened"
        self.receive(3, 2, 5)
        api = self.env["pos.order"]
        # Desde la Fase 1 (venta con falta de stock), la falta ya no lanza
        # excepción: se agrega por producto y se devuelve como "deficit" para
        # que el TPV pida confirmación, no para bloquear sin salida.
        result = api.mgs_check_stock(self.session.id, [
            {"product_id": self.flower.id, "qty": 2},
            {"product_id": self.flower.id, "qty": 2},
        ])
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["deficits"]), 1)
        deficit = result["deficits"][0]
        self.assertEqual(deficit["product_id"], self.flower.id)
        self.assertEqual(deficit["available"], 3)
        self.assertEqual(deficit["requested"], 4)
        self.assertEqual(deficit["missing"], 1)
        self.assertTrue(api.mgs_check_stock(self.session.id, [{"product_id": self.flower.id, "qty": 3}])["ok"])
        order = self.order(3)
        order._create_order_picking()
        order.state = "paid"
        self.assertTrue(api.mgs_check_stock(self.session.id, [{"product_id": self.flower.id, "qty": 3}], order.uuid)["already_confirmed"])

    def test_hardware_requests_are_idempotent_and_cash_specific(self):
        self.receive(3, 2, 5)
        order = self.order(1)
        order._create_order_picking()
        order.state = "paid"
        config = self.env["mgs.config"]
        first = config.mgs_pos_print_order(order.id)
        second = config.mgs_pos_print_order(order.id)
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["existing"])
        with self.assertRaises(UserError):
            config.mgs_pos_open_drawer(order.id)
        order.add_payment({"pos_order_id": order.id, "payment_method_id": self.cash_payment_method.id, "amount": 10})
        first = config.mgs_pos_open_drawer(order.id)
        second = config.mgs_pos_open_drawer(order.id)
        self.assertEqual(first["id"], second["id"])

    def test_ticket_carries_the_simplified_invoice_details(self):
        """Contenido del artículo 7 del RD 1619/2012 que sí depende de nosotros.

        Lo que la ley pide y el ticket tiene que decir: identificación y NIF de
        la tienda, número, fecha, descripción, tipo impositivo, total, y en las
        rectificativas la referencia al ticket rectificado."""
        self.receive(5, 2, 3)
        tax = self.env["account.tax"].create({
            "name": "21% G", "amount": 21.0, "amount_type": "percent",
            "type_tax_use": "sale", "company_id": self.env.company.id,
        })
        self.env.company.write({"vat": "ESB12345674", "street": "Calle de prueba 1", "city": "Madrid"})
        sale = self.order(2)
        sale.lines.write({"tax_ids": [Command.set(tax.ids)], "price_subtotal": 20,
                          "price_subtotal_incl": 24.2})
        config = self.env["mgs.config"]._mgs_get()
        ticket = config._mgs_pos_ticket(sale).to_bytes().decode("cp858", errors="replace")
        self.assertIn(self.env.company.name, ticket)
        self.assertIn("ESB12345674", ticket)
        self.assertIn(sale.name, ticket)
        self.assertIn("Rosa TPV", ticket)
        # El tipo impositivo, no el nombre interno del impuesto de l10n_es.
        self.assertIn("IVA 21%", ticket)
        self.assertNotIn("21% G", ticket)
        self.assertNotIn("Rectifica", ticket)

        refund = self.order(-1, sale.lines)
        refund_ticket = config._mgs_pos_ticket(refund).to_bytes().decode("cp858", errors="replace")
        self.assertIn("Rectifica el ticket %s" % sale.name, refund_ticket)

    def test_ticket_lines_never_overflow_the_configured_paper_width(self):
        """Hallazgo de revisión: el nombre de la empresa, la dirección, el
        nombre de la clienta y el pie del ticket se imprimían con `ln()` sin
        pasar por `wrapped()` — con un dato largo de verdad (habitual en
        nombres y apellidos, o en una dirección completa) se desbordaban del
        ancho de la impresora térmica en vez de partirse en varias líneas."""
        self.receive(2, 2, 3)
        # Sin logo: es una imagen en bytes binarios (puede contener 0x0A
        # sueltos) y se sale del alcance de esta prueba, que es sobre el
        # ajuste del TEXTO a columnas, no sobre la imagen.
        self.env.company.logo = False
        self.env.company.write({
            "street": "Avenida de la Constitución Española número 128, local 3, bajo derecha",
            "city": "Barcelona",
        })
        config = self.env["mgs.config"]._mgs_get()
        config.receipt_footer = (
            "¡Gracias por confiar en nosotras y esperamos verte muy pronto de "
            "nuevo por la floristería!")
        partner = self.env["res.partner"].create({
            "name": "María del Carmen Fernández Rodríguez de la Torre y Gómez"})
        sale = self.order(1)
        sale.partner_id = partner
        ticket = config._mgs_pos_ticket(sale).to_bytes().decode("cp858", errors="replace")
        width = config._mgs_doc().width
        # Se corta justo tras el pie: lo que va después (código de barras,
        # corte de papel) es un bloque de bytes binario de longitud variable,
        # no texto en columnas, y no es lo que se está probando aquí.
        footer_end = ticket.index("floristería") + len("floristería")
        body = ticket[:footer_end]
        # Los únicos comandos ESC/POS que aparecen antes del pie son estos,
        # todos de longitud fija (init, página de códigos, alinear, negrita,
        # tamaño): ni llevan '\n' propio ni ocupan columna impresa, así que
        # se quitan antes de medir el ancho de cada línea de texto real.
        visible_body = re.sub(r"\x1b@|\x1bt.|\x1ba.|\x1bE.|\x1d!.", "", body, flags=re.DOTALL)
        for line in visible_body.splitlines():
            self.assertLessEqual(
                len(line), width,
                "línea más larga que el papel (%s > %s): %r" % (len(line), width, line))
        # Ningún dato desaparece por el camino: solo se reparte en más líneas.
        self.assertIn(partner.name.split()[-1], ticket)
        self.assertIn("floristería", ticket)

    def test_ticket_has_no_qr_when_nothing_is_configured(self):
        """Sin «Enlace a Google Reseñas», sin web de la tienda y sin la
        facturación por cuenta propia del TPV activada, el ticket térmico no
        debe llevar ningún comando QR (GS ( k) — solo el código de barras del
        número de venta."""
        self.receive(1, 2, 3)
        sale = self.order(1)
        config = self.env["mgs.config"]._mgs_get()
        ticket = config._mgs_pos_ticket(sale).to_bytes()
        self.assertNotIn(b"\x1d(k", ticket)

    def test_ticket_and_pdf_print_the_same_review_and_website_qr(self):
        """Hallazgo: el ticket en PDF (report/pos_order_receipt_report.xml,
        vía mgs_pos_receipt.py) sabía dibujar el QR de la reseña de Google y
        el de la web, pero `_mgs_pos_ticket` (el que de verdad sale por la
        impresora térmica) nunca llamaba a `doc.qr()` — la primitiva estaba
        implementada en mgs_escpos.py y sin usar. Debe llevarlos igual que el
        PDF: mismos datos, mismo origen de configuración."""
        self.receive(1, 2, 3)
        config = self.env["mgs.config"]._mgs_get()
        config.google_review_url = "https://g.page/r/prueba/review"
        sale = self.order(1)
        # Sobre la compañía de LA VENTA, no sobre self.env.company: en esta
        # suite (TestPointOfSaleCommon) no son necesariamente el mismo
        # registro, y _mgs_receipt_website_url() lee company_id.partner_id
        # de la propia venta. Con el esquema puesto ("https://..."): sin
        # esquema, res.partner._clean_website() (odoo/addons/base) antepone
        # "http://" ella sola al escribir, antes de que este módulo llegue a
        # decidir nada.
        sale.company_id.partner_id.website = "https://clavelyazahar.es"
        self.assertEqual(sale._mgs_receipt_website_url(), "https://clavelyazahar.es")
        ticket = config._mgs_pos_ticket(sale).to_bytes()
        # doc.qr() manda 5 subcomandos GS ( k por cada QR: dos QR (reseña y
        # web) deben dejar 10 en total.
        self.assertEqual(ticket.count(b"\x1d(k"), 2 * 5)
        self.assertIn(b"https://g.page/r/prueba/review", ticket)
        self.assertIn(b"https://clavelyazahar.es", ticket)

        # Mismos datos que expone el modelo al informe PDF.
        self.assertEqual(sale._mgs_receipt_review_url(), config.google_review_url)
        self.assertTrue(sale._mgs_receipt_review_qr())
        self.assertTrue(sale._mgs_receipt_website_qr())

    def test_ticket_and_pdf_offer_the_invoice_request_qr_when_enabled(self):
        """Hallazgo relacionado: el recibo nativo del TPV enseña un QR para
        pedir la factura online (`pos_qr_code` en point_of_sale) cuando el
        ticket se imprime por el navegador, pero ni el PDF de este módulo ni
        el ticket ESC/POS lo llevaban — una venta reimpresa como PDF, o
        sacada por la térmica, se quedaba sin él aunque el ajuste de la
        compañía estuviera activado."""
        self.receive(1, 2, 3)
        self.env.company.point_of_sale_use_ticket_qr_code = True
        sale = self.order(1)
        sale.write({"state": "paid", "ticket_code": "ab12c"})
        config = self.env["mgs.config"]._mgs_get()

        self.assertTrue(sale._mgs_receipt_invoice_qr_ready())
        self.assertTrue(sale._mgs_receipt_invoice_qr())
        self.assertIn("/pos/ticket/", sale._mgs_receipt_invoice_portal_url())

        doc = config._mgs_pos_ticket(sale)
        self.assertIn(b"\x1d(k", doc.to_bytes())
        self.assertIn("Código: ab12c", doc.to_bytes().decode("cp858", errors="replace"))

        # Una venta sin cobrar (borrador) o sin código único no lo enseña:
        # son las mismas condiciones que usa el recibo de pantalla nativo.
        draft = self.order(1)
        self.assertFalse(draft._mgs_receipt_invoice_qr_ready())
        sale.ticket_code = False
        self.assertFalse(sale._mgs_receipt_invoice_qr_ready())

    def test_pos_hardware_info_carries_the_same_qr_for_the_screen_receipt(self):
        """Hallazgo: el recibo EN PANTALLA del TPV (point_of_sale.OrderReceipt,
        parcheado por mi_gestor_stock/static/src/xml/pos_receipt.xml) no
        sabía nada del QR de reseña de Google ni del de la web — solo el
        ticket térmico y el PDF de reimpresión los llevaban. `pos_hardware.js`
        pide estos datos una vez al abrir sesión (mgs_pos_hardware_info) y
        los añade a cada recibo impreso (orderExportForPrinting); esto
        prueba el lado de servidor de ese contrato."""
        config = self.env["mgs.config"]._mgs_get()
        config.google_review_url = "https://g.page/r/prueba/review"
        self.env.company.partner_id.website = "https://clavelyazahar.es"
        info = config.mgs_pos_hardware_info()
        self.assertTrue(info["review_qr"])
        self.assertTrue(info["website_qr"])
        self.assertEqual(info["website_url"], "https://clavelyazahar.es")

        config.google_review_url = False
        self.env.company.partner_id.website = False
        info = config.mgs_pos_hardware_info()
        self.assertFalse(info["review_qr"])
        self.assertFalse(info["website_qr"])
        self.assertFalse(info["website_url"])
