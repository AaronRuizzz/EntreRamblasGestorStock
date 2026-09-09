from datetime import datetime, timedelta

import pytz

from odoo import Command, fields
from odoo.exceptions import UserError, AccessError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged("post_install", "-at_install")
class TestEvent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Novia de prueba"})
        # Arco: se alquila, sale y vuelve.
        cls.arch = cls.env["product.product"].create({
            "name": "Arco floral", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "mgs_rental_ok": True, "mgs_rental_deposit": 50.0,
            "list_price": 120.0,
        })
        # Centro de mesa: se vende, no vuelve.
        cls.centre = cls.env["product.product"].create({
            "name": "Centro de mesa", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "list_price": 30.0,
        })
        # "Hoy" en el sentido del informe (ver mgs_monthly_report._mgs_period):
        # el día de Madrid, no el de UTC. Cerca de la medianoche española
        # (verano, UTC+2) ambos difieren, y un cobro fechado "ahora mismo"
        # quedaría fuera de la ventana del informe si aquí se usara
        # fields.Date.today() (UTC) a secas.
        cls.today = datetime.now(pytz.timezone("Europe/Madrid")).date()

    def stock(self, product, quantity, cost=10.0):
        self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
        })]}).action_confirm()

    def event(self, days=30, length=1, lines=None):
        start = self.today + timedelta(days=days)
        return self.env["mgs.event"].create({
            "partner_id": self.customer.id,
            "event_date": start,
            "return_date": start + timedelta(days=length),
            "line_ids": lines if lines is not None else [
                Command.create({"product_id": self.arch.id, "is_rental": True,
                                "quantity": 1, "unit_price": 120.0}),
                Command.create({"product_id": self.centre.id, "is_rental": False,
                                "quantity": 4, "unit_price": 30.0}),
            ],
        })

    # ------------------------------------------------------------------
    def test_event_reference_uses_the_new_prefix_not_boda(self):
        """La numeración pasó de BODA/ a EVENTO/ (ver
        res_company._mgs_apply_event_sequence); esto fija que test.ps1 lo
        note si alguna vez el prefijo se queda a medias tras un `-u`."""
        event = self.event()
        self.assertTrue(event.name.startswith("EVENTO/"), event.name)
        self.assertNotIn("BODA", event.name)

    def test_quote_reserves_without_moving_stock(self):
        self.stock(self.arch, 1)
        self.stock(self.centre, 10)
        event = self.event()
        self.assertEqual(event.amount_total, 120 + 4 * 30)
        self.assertEqual(event.amount_deposit, 50.0)
        self.assertEqual(event.amount_due, 240.0)
        # Un presupuesto sin aceptar no compromete nada.
        self.assertEqual(self.arch.mgs_rental_available(event.event_date, event.return_date), 1)
        event.action_confirm()
        # Aceptado: comprometido, pero la mercancía sigue en la tienda.
        self.assertEqual(self.arch.mgs_rental_available(event.event_date, event.return_date), 0)
        self.assertEqual(self.arch.qty_available, 1)
        self.assertEqual(self.centre.qty_available, 10)
        self.assertFalse(event.move_ids)

    def test_the_same_arch_cannot_go_to_two_weddings_the_same_day(self):
        self.stock(self.arch, 1)
        self.stock(self.centre, 10)
        first = self.event(days=30)
        first.action_confirm()
        # Otro evento que se solapa: no hay arco libre.
        clash = self.event(days=30)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            clash.action_confirm()
        # Y una que no se solapa sí entra.
        later = self.event(days=90)
        later.action_confirm()
        self.assertEqual(later.state, "confirmed")

    def test_overlap_is_checked_on_the_whole_range_not_just_the_day(self):
        self.stock(self.arch, 1)
        booked = self.event(days=30, length=5)
        booked.action_confirm()
        # Empieza dentro del rango del anterior aunque sea otro día.
        overlapping = self.event(days=33, length=1)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            overlapping.action_confirm()

    def test_delivery_moves_rental_out_but_not_to_the_customer(self):
        self.stock(self.arch, 2)
        self.stock(self.centre, 10)
        event = self.event()
        event.action_confirm()
        event.action_deliver()
        rental_location = self.env.ref("mi_gestor_stock.stock_location_rental")
        # El arco sale de la tienda pero sigue siendo nuestro.
        self.assertEqual(self.arch.qty_available, 1)
        self.assertEqual(self.arch.mgs_rental_fleet(), 2)
        arch_move = event.move_ids.filtered(lambda m: m.product_id == self.arch)
        self.assertEqual(arch_move.location_dest_id, rental_location)
        self.assertEqual(arch_move.state, "done")
        # El centro de mesa se vende: se va al cliente y deja de ser nuestro.
        centre_move = event.move_ids.filtered(lambda m: m.product_id == self.centre)
        self.assertEqual(centre_move.location_dest_id.usage, "customer")
        self.assertEqual(self.centre.qty_available, 6)
        self.assertEqual(self.centre.mgs_rental_fleet(), 6)
        self.assertTrue(event.pending_return)

    def test_return_puts_whole_items_back_and_scraps_the_broken_ones(self):
        self.stock(self.arch, 3, cost=40.0)
        event = self.event(lines=[Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 3, "unit_price": 120.0})])
        event.action_confirm()
        event.action_deliver()
        self.assertEqual(self.arch.qty_available, 0)
        # Vuelven dos enteros y uno roto.
        event.line_ids.write({"return_ok_qty": 2, "return_damaged_qty": 1})
        event.action_register_return()
        self.assertEqual(self.arch.qty_available, 2)
        self.assertEqual(event.line_ids.returned_qty, 2)
        self.assertEqual(event.line_ids.damaged_qty, 1)
        self.assertFalse(event.pending_return)
        # El roto sale como merma, con su coste real y motivo de rotura.
        scrap = self.env["stock.scrap"].search(
            [("product_id", "=", self.arch.id)], order="id desc", limit=1)
        self.assertEqual(scrap.state, "done")
        self.assertEqual(scrap.scrap_qty, 1)
        self.assertEqual(scrap.mgs_reason, "breakage")
        # Ya no queda nada fuera: la flota baja a 2, la rota desaparece.
        self.assertEqual(self.arch.mgs_rental_fleet(), 2)

    def test_material_still_out_blocks_closing_the_event(self):
        self.stock(self.arch, 1)
        event = self.event(lines=[Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 1, "unit_price": 100.0})])
        event.action_confirm()
        event.action_deliver()
        event.action_register_payment(100.0)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_done()
        event.line_ids.write({"return_ok_qty": 1})
        event.action_register_return()
        event.action_done()
        self.assertEqual(event.state, "done")

    def test_cannot_return_more_than_went_out(self):
        self.stock(self.arch, 2)
        event = self.event(lines=[Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 2, "unit_price": 100.0})])
        event.action_confirm()
        event.action_deliver()
        event.line_ids.write({"return_ok_qty": 3})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_register_return()

    def test_payments_are_the_deposit_then_the_rest(self):
        self.stock(self.centre, 10)
        event = self.event(lines=[Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 4, "unit_price": 25.0})])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_register_payment(50.0)  # aún es presupuesto
        event.action_confirm()
        event.action_register_payment(30.0, "card", "Señal")
        self.assertEqual(event.amount_paid, 30.0)
        self.assertEqual(event.amount_due, 70.0)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_register_payment(999.0)  # más de lo pendiente
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_register_payment(-10.0)
        event.action_deliver()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_done()  # queda por cobrar
        event.action_register_payment(70.0)
        event.action_done()
        self.assertEqual(event.state, "done")
        # Un cobro registrado no se toca.
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            event.payment_ids[0].write({"amount": 1})

    def test_confirm_needs_real_stock_and_valid_lines(self):
        # Sin recepción previa: el arco no tiene ni una unidad.
        # Sin existencias del arco no se puede comprometer.
        event = self.event(lines=[Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 1, "unit_price": 100.0})])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.action_confirm()
        # Marcar como alquiler algo que no se alquila tampoco vale.
        self.stock(self.centre, 5)
        bad = self.event(lines=[Command.create({
            "product_id": self.centre.id, "is_rental": True,
            "quantity": 1, "unit_price": 10.0})])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            bad.action_confirm()

    def test_dates_and_edits_are_guarded(self):
        self.stock(self.centre, 5)
        event = self.event(lines=[Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 1, "unit_price": 10.0})])
        # Devolución antes del evento.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.write({"return_date": event.event_date - timedelta(days=2)})
            event.action_confirm()
        event.action_confirm()
        # Un evento aceptado ya no se edita.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.write({"note": "cambio tardío"})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.unlink()

    def test_only_the_owner_touches_events(self):
        staff = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
            login="event_staff", groups="mi_gestor_stock.group_mgs_user",
            company_id=self.env.company.id)
        self.stock(self.centre, 5)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.env["mgs.event"].with_user(staff).create({
                "partner_id": self.customer.id, "event_date": self.today,
                "return_date": self.today})
        event = self.event(lines=[Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 1, "unit_price": 10.0})])
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            event.with_user(staff).action_confirm()

    def test_a_rented_product_must_be_tracked(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env["product.product"].create({
                "name": "Arco imposible", "mgs_rental_ok": True, "is_storable": False,
                "type": "service"})

    def test_a_bouquet_composition_without_components_cannot_go_into_a_wedding(self):
        """Una composicion (ramo a medida) sin materiales no descontaria nada
        al entregar: action_deliver() no sabria que flor sacar. Antes se podia
        meter en un evento asi y la merma de flor se perdia en silencio; ahora
        hace falta indicar de que esta hecha para poder anadir la partida (ver
        test_a_bouquet_composition_delivers_each_component)."""
        bouquet = self.env["product.product"].create({
            "name": "Ramo a medida de prueba", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "list_price": 40.0,
        })
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.event(lines=[Command.create({
                "product_id": bouquet.id, "quantity": 1, "unit_price": 40.0})])
        # Tampoco por la via de anadir la linea a un presupuesto ya creado.
        event = self.event(lines=[Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 1, "unit_price": 30.0})])
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.write({"line_ids": [Command.create({
                "product_id": bouquet.id, "quantity": 1, "unit_price": 40.0})]})

    def test_a_genuine_service_line_still_delivers_without_stock(self):
        """Un servicio de verdad (montaje, transporte...) no es una
        composicion: no lleva existencias porque no tiene, no porque se le
        haya escondido el descuento. Tiene que poder seguir entregandose sin
        mover stock, para no confundir este caso con el de la prueba anterior."""
        service = self.env["product.product"].create({
            "name": "Montaje en el salon", "is_storable": False, "type": "service",
            "list_price": 60.0,
        })
        self.stock(self.centre, 10)
        event = self.event(lines=[
            Command.create({"product_id": self.centre.id, "is_rental": False,
                            "quantity": 4, "unit_price": 30.0}),
            Command.create({"product_id": service.id, "is_rental": False,
                            "quantity": 1, "unit_price": 60.0}),
        ])
        event.action_confirm()
        event.action_deliver()
        self.assertEqual(event.state, "delivered")
        self.assertFalse(event.move_ids.filtered(lambda m: m.product_id == service))
        self.assertTrue(event.move_ids.filtered(lambda m: m.product_id == self.centre))

    def test_events_appear_in_the_monthly_report_without_double_counting(self):
        self.stock(self.centre, 10)
        event = self.event(days=0, lines=[Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 4, "unit_price": 25.0})])
        event.action_confirm()
        event.action_register_payment(40.0, "cash", "Señal")
        report = self.env["mgs.monthly.report"].create({
            "date_from": self.today, "date_to": self.today})
        data = report.mgs_get_report_data()
        self.assertTrue(data["events_available"])
        self.assertEqual(len(data["event_rows"]), 1)
        row = data["event_rows"][0]
        self.assertEqual(row["total"], 100.0)
        self.assertEqual(row["paid"], 40.0)
        self.assertEqual(row["due"], 60.0)
        self.assertEqual(data["event_total"], 100.0)
        self.assertEqual(data["event_collected"], 40.0)
        # No se cuela en las ventas de mostrador: eso sería contarlo dos veces.
        self.assertEqual(data["total_revenue"], 0.0)
        # Un evento cancelado desaparece del informe.
        event.action_cancel()
        self.assertEqual(len(report.mgs_get_report_data()["event_rows"]), 0)

    def test_report_filtered_by_category_hides_events(self):
        """Un evento mezcla categorías: repartirlo entre ellas sería inventar."""
        self.stock(self.centre, 10)
        event = self.event(days=0, lines=[Command.create({
            "product_id": self.centre.id, "is_rental": False,
            "quantity": 1, "unit_price": 25.0})])
        event.action_confirm()
        report = self.env["mgs.monthly.report"].create({
            "date_from": self.today, "date_to": self.today,
            "category_id": self.centre.categ_id.id})
        data = report.mgs_get_report_data()
        self.assertFalse(data["events_available"])
        self.assertEqual(data["event_rows"], [])

    def test_quote_pdf_shows_the_customer_what_is_rented(self):
        self.stock(self.arch, 1)
        self.stock(self.centre, 10)
        event = self.event()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mi_gestor_stock.action_report_mgs_event", event.ids)[0].decode()
        self.assertIn("Arco floral", html)
        self.assertIn("alquiler, se devuelve", html)
        self.assertIn("Centro de mesa", html)
        self.assertIn("Fianza del material", html)

    def test_return_can_be_annotated_the_way_the_form_saves_it(self):
        """El formulario guarda el EVENTO con un comando sobre `line_ids`.

        Escribir directo en la línea (como hacen las otras pruebas) no pasa por
        el mismo sitio: sin esta prueba, anotar la devolución desde la pantalla
        chocaba con «solo se edita un presupuesto sin aceptar»."""
        self.stock(self.arch, 2)
        event = self.event(lines=[Command.create({
            "product_id": self.arch.id, "is_rental": True,
            "quantity": 2, "unit_price": 100.0})])
        event.action_confirm()
        event.action_deliver()
        line = event.line_ids
        # Exactamente lo que manda el formulario al guardar.
        event.write({"line_ids": [Command.update(line.id, {"return_ok_qty": 1,
                                                           "return_damaged_qty": 1})]})
        event.action_register_return()
        self.assertEqual(line.returned_qty, 1)
        self.assertEqual(line.damaged_qty, 1)
        self.assertEqual(self.arch.qty_available, 1)
        # Pero por esa misma vía no se puede cambiar nada más.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.write({"line_ids": [Command.update(line.id, {"quantity": 99})]})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.write({"line_ids": [Command.create({"product_id": self.centre.id,
                                                      "quantity": 1, "unit_price": 5})]})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            event.write({"note": "no se toca"})

    def test_a_bouquet_composition_delivers_each_component(self):
        """Cierra la sección "0.2": una composición SÍ puede ir en un evento,
        siempre que lleve sus materiales — entonces se entrega descontando cada
        flor, no la composición (que no tiene existencias propias)."""
        rose = self.env["product.product"].create({
            "name": "Rosa de composicion de evento", "is_storable": True, "tracking": "lot",
            "mgs_auto_lots": True, "use_expiration_date": True,
        })
        centre_compo = self.env["product.product"].create({
            "name": "Centro de mesa a medida", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "list_price": 40.0,
        })
        self.stock(rose, 100)
        event = self.event(lines=[Command.create({
            "product_id": centre_compo.id,
            "component_ids": [Command.create({"product_id": rose.id, "quantity": 6})],
            "is_rental": False, "quantity": 3, "unit_price": 40.0})])
        event.action_confirm()
        event.action_deliver()
        # 3 centros x 6 rosas cada uno = 18 rosas, no "3 unidades de centro".
        self.assertEqual(rose.qty_available, 100 - 18)
        self.assertEqual(centre_compo.qty_available, 0.0)  # no tiene existencias propias
        moves = event.move_ids.filtered(lambda m: m.product_id == rose)
        self.assertEqual(sum(moves.mapped("product_uom_qty")), 18)
        self.assertEqual(event.line_ids.delivered_qty, 3)

    def test_a_composition_without_components_is_rejected_even_by_write(self):
        centre_compo = self.env["product.product"].create({
            "name": "Centro sin materiales", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "list_price": 40.0,
        })
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.event(lines=[Command.create({
                "product_id": centre_compo.id, "quantity": 1, "unit_price": 40.0})])

    def test_components_on_a_non_composition_product_are_rejected(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.event(lines=[Command.create({
                "product_id": self.centre.id,
                "component_ids": [Command.create({"product_id": self.centre.id, "quantity": 1})],
                "is_rental": False, "quantity": 1, "unit_price": 30.0})])
