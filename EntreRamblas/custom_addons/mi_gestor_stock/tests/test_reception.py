from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestReception(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Rosa prueba partidas", "is_storable": True,
            "tracking": "lot", "use_expiration_date": True,
        })

    def receive(self, quantity=10, cost=2, days=3):
        wizard = self.env["mgs.reception"].create({
            "line_ids": [Command.create({
                "product_id": self.product.id, "quantity": quantity,
                "unit_cost": cost,
                "expiry_date": fields.Date.today() + timedelta(days=days),
            })],
        })
        wizard.action_confirm()
        return wizard

    def test_two_receipts_preserve_lots_costs_and_expiry(self):
        first = self.receive(cost=2, days=3)
        second = self.receive(cost=4, days=8)
        self.assertEqual(first.picking_id.state, "done")
        self.assertEqual(second.picking_id.state, "done")
        lots = (first.picking_id | second.picking_id).move_line_ids.lot_id
        self.assertEqual(len(lots), 2)
        self.assertEqual(sorted(lots.mapped("mgs_unit_cost")), [2, 4])
        self.assertEqual(self.product.qty_available, 20)
        self.product.standard_price = 99
        self.assertEqual(sorted(lots.mapped("mgs_unit_cost")), [2, 4])
        self.assertEqual(self.product.mgs_expiry_date, fields.Date.today() + timedelta(days=3))
        with self.assertRaises(ValidationError):
            lots[0].write({"mgs_unit_cost": 99})

    def test_confirm_twice_does_not_receive_twice(self):
        wizard = self.receive()
        picking = wizard.picking_id
        wizard.action_confirm()
        self.assertEqual(wizard.picking_id, picking)
        self.assertEqual(self.product.qty_available, 10)

    def test_invalid_quantity_and_cost(self):
        for quantity, cost in [(0, 2), (-1, 2), (1, -2)]:
            with self.assertRaises(UserError), self.env.cr.savepoint():
                self.receive(quantity=quantity, cost=cost)

    def test_scanning_does_not_reuse_previous_expiry(self):
        self.product.barcode = "MGS-ROSA-TEST"
        self.receive()
        wizard = self.env["mgs.reception"].new({})
        wizard.on_barcode_scanned(self.product.barcode)
        wizard.on_barcode_scanned(self.product.barcode)
        self.assertEqual(len(wizard.line_ids), 1)
        self.assertEqual(wizard.line_ids.quantity, 2)
        self.assertFalse(wizard.line_ids.expiry_date)

    def outgoing(self, quantity):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        move = self.env["stock.move"].create({
            "name": "Venta prueba", "product_id": self.product.id,
            "product_uom": self.product.uom_id.id, "product_uom_qty": quantity,
            "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": self.env.ref("stock.stock_location_customers").id,
        })
        move._action_confirm(merge=False)
        move._add_mls_related_to_order(self.env["pos.order.line"])
        move._action_done()
        return move

    def test_sale_consumes_earliest_expiry_and_freezes_cost(self):
        later = self.receive(quantity=10, cost=4, days=8)
        earlier = self.receive(quantity=5, cost=2, days=3)
        move = self.outgoing(7)
        quantities = {line.lot_id.id: line.quantity for line in move.move_line_ids}
        self.assertEqual(quantities[earlier.picking_id.move_line_ids.lot_id.id], 5)
        self.assertEqual(quantities[later.picking_id.move_line_ids.lot_id.id], 2)
        self.assertEqual(sum(line.quantity * line.mgs_unit_cost for line in move.move_line_ids), 18)
        self.product.standard_price = 100
        self.assertEqual(sum(line.quantity * line.mgs_unit_cost for line in move.move_line_ids), 18)
        self.assertEqual(self.product.qty_available, 8)

    def test_expired_stock_is_not_available_for_sale(self):
        self.receive(quantity=10, days=-2)
        self.receive(quantity=3, days=2)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.outgoing(4)
        self.assertEqual(self.product.qty_available, 13)
        self.assertFalse(self.env["stock.quant"].search([
            ("product_id", "=", self.product.id), ("reserved_quantity", ">", 0),
        ]))

    def test_insufficient_stock_rolls_back_reservations(self):
        self.receive(quantity=3)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.outgoing(4)
        self.assertEqual(self.product.qty_available, 3)

    def test_new_product_uses_florist_defaults_when_no_category_is_chosen(self):
        wizard = self.env["mgs.reception"].create({
            "mode": "nuevo", "new_name": "Peonía rosa",
            "new_barcode": "8499999999990", "new_price": 3.5, "new_cost": 1.2,
        })
        self.assertEqual(wizard.new_categ_id.name, "Flor cortada")
        self.assertEqual(wizard.new_tax_id.amount, 21)
        wizard.action_add_new_product()
        product = self.env["product.template"].search([("name", "=", "Peonía rosa")])
        self.assertEqual(product.categ_id, wizard._mgs_default_category())
        self.assertEqual(product.taxes_id, wizard._mgs_default_sale_tax())

    def test_margin_calculator_computes_price_from_cost_and_margin(self):
        # Margen sobre el PRECIO DE VENTA, como en una calculadora financiera:
        # coste 10 €, margen 30 % (preset por defecto) -> 14,29 € sin IVA,
        # 17,29 € con el 21 % (tipo por defecto, ver
        # test_new_product_uses_florist_defaults_when_no_category_is_chosen).
        form = Form(self.env["mgs.reception"])
        form.mode = "nuevo"
        form.new_cost = 10.0
        self.assertAlmostEqual(form.new_price, 10 / 0.7, places=2)
        self.assertAlmostEqual(form.new_price_taxed, (10 / 0.7) * 1.21, places=2)
        self.assertAlmostEqual(form.new_margin_amount, (10 / 0.7) - 10, places=2)

    def test_margin_of_100_percent_or_more_does_not_crash(self):
        form = Form(self.env["mgs.reception"])
        form.mode = "nuevo"
        form.new_cost = 10.0
        previous_price = form.new_price
        form.new_margin_preset = "otro"
        form.new_margin = 100.0
        self.assertEqual(form.new_price, previous_price)
        form.new_margin = 150.0
        self.assertEqual(form.new_price, previous_price)

    def test_typing_the_price_by_hand_recalculates_the_margin(self):
        form = Form(self.env["mgs.reception"])
        form.mode = "nuevo"
        form.new_cost = 10.0
        form.new_price = 20.0
        self.assertAlmostEqual(form.new_margin, 50.0, places=1)
        self.assertEqual(form.new_margin_preset, "otro")

    def test_rental_ok_is_saved_on_the_new_product_and_shown_on_the_line(self):
        wizard = self.env["mgs.reception"].create({
            "mode": "nuevo", "new_name": "Arco de flores", "new_barcode": "8499999999992",
            "new_price": 50.0, "new_cost": 20.0,
            "new_rental_ok": True, "new_rental_deposit": 30.0,
        })
        wizard.action_add_new_product()
        product = self.env["product.template"].search([("name", "=", "Arco de flores")])
        self.assertTrue(product.mgs_rental_ok)
        self.assertEqual(product.mgs_rental_deposit, 30.0)
        line = wizard.line_ids.filtered(lambda l: l.product_id.product_tmpl_id == product)
        self.assertTrue(line.rental_ok)

    def test_reception_has_a_human_title_after_the_wizard_is_saved(self):
        wizard = self.env["mgs.reception"].create({})
        self.assertEqual(wizard.display_name, "Recepción de mercancía")

    def test_form_can_be_saved_after_creating_a_new_product(self):
        # Hallazgo 18, prueba del RECORRIDO DEL FORMULARIO (no solo del
        # método de negocio): Producto nuevo -> rellenar -> Crear y añadir ->
        # Guardar en almacén. action_add_new_product limpiaba new_categ_id
        # pero dejaba mode="nuevo"; la vista exige esa categoría en ese modo
        # (required="mode == 'nuevo'"), así que el siguiente guardado del
        # asistente (lo que hace "Guardar en almacén") fallaba con «Campos no
        # válidos: Categoría» aunque el producto ya se hubiera creado.
        form = Form(self.env["mgs.reception"])
        form.mode = "nuevo"
        form.new_name = "Peonía rosa de formulario"
        form.new_barcode = "8499999999991"
        form.new_price = 3.5
        form.new_cost = 1.2
        form.new_categ_id = self.env["product.category"].create({"name": "Planta de temporada 2"})
        wizard = form.save()

        wizard.action_add_new_product()
        self.assertEqual(wizard.mode, "existente")

        # Reabrir el asistente en un Form (como hace el cliente antes de
        # "Guardar en almacén") y guardar: antes del arreglo, esto lanzaba
        # ValidationError por el campo requerido de la categoría.
        reloaded = Form(wizard)
        reloaded.save()

    def test_factory_categories_are_archived_and_hidden(self):
        for xmlid in ("product.product_category_all", "product.product_category_1",
                      "product.cat_expense", "point_of_sale.product_category_pos"):
            self.assertFalse(self.env.ref(xmlid).active, xmlid)
        visible = self.env["product.category"].search([])
        self.assertFalse(visible & self.env.ref("product.product_category_all"))

    def test_scrap_records_lot_cost_actor_and_is_idempotent(self):
        receipt = self.receive(quantity=4, cost=3)
        scrap = self.env["stock.scrap"].create({
            "product_id": self.product.id, "lot_id": receipt.picking_id.move_line_ids.lot_id.id,
            "scrap_qty": 2, "mgs_reason": "deterioration",
        })
        scrap.do_scrap()
        scrap.do_scrap()
        self.assertEqual(self.product.qty_available, 2)
        self.assertEqual(scrap.mgs_validated_by, self.env.user)
        self.assertEqual(scrap.move_ids.move_line_ids.mgs_unit_cost, 3)
        excessive = scrap.copy({"scrap_qty": 3})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            excessive.do_scrap()
