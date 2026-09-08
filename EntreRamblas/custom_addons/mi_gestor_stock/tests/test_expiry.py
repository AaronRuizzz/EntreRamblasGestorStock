from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged, new_test_user


@tagged("post_install", "-at_install")
class TestExpiry(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rose = cls.env["product.product"].create({
            "name": "Rosa de caducidad", "is_storable": True, "tracking": "lot",
            "use_expiration_date": True,
        })
        cls.config = cls.env["mgs.config"]._mgs_get()
        cls.config.expiry_grace_days = 2

    def receive(self, quantity, days, cost=2.0):
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": self.rose.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def detect(self):
        self.env["mgs.expiry.writeoff"]._mgs_cron_detect_expired()
        return self.env["mgs.expiry.writeoff"].search([
            ("company_id", "=", self.env.company.id), ("state", "=", "proposed")], limit=1)

    # ------------------------------------------------------------------
    def test_within_grace_period_is_not_proposed(self):
        """Caducó ayer, margen de 2 días: todavía no se propone."""
        self.receive(10, days=-1)
        proposal = self.detect()
        self.assertFalse(proposal)

    def test_past_grace_period_is_proposed(self):
        """Caducó hace 5 días, margen de 2: sí se propone, con el coste real."""
        self.receive(10, days=-5, cost=3.0)
        proposal = self.detect()
        self.assertTrue(proposal)
        self.assertEqual(len(proposal.line_ids), 1)
        self.assertEqual(proposal.line_ids.quantity, 10)
        self.assertEqual(proposal.line_ids.unit_cost, 3.0)
        self.assertEqual(proposal.total_cost, 30.0)

    def test_the_cron_refreshes_instead_of_duplicating(self):
        self.receive(10, days=-5)
        first = self.detect()
        second = self.detect()
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(second.line_ids), 1)
        # Si ya no queda nada caducado, la propuesta se vacía, no desaparece
        # (sigue siendo la misma propuesta abierta, ahora sin partidas).
        self.receive(5, days=30)  # producto nuevo, no caducado: no cambia nada
        third = self.detect()
        self.assertEqual(third.id, first.id)

    def test_confirm_scraps_and_a_second_confirm_is_rejected_not_repeated(self):
        self.receive(10, days=-5, cost=2.0)
        proposal = self.detect()
        self.assertEqual(self.rose.qty_available, 10)
        proposal.action_confirm()
        self.assertEqual(proposal.state, "confirmed")
        self.assertEqual(self.rose.qty_available, 0)
        scraps = self.env["stock.scrap"].search([("mgs_expiry_line_id", "=", proposal.line_ids.id)])
        self.assertEqual(len(scraps), 1)
        self.assertEqual(scraps.mgs_reason, "expiry")

        # Doble clic: no se puede volver a confirmar ni duplicar la merma.
        with self.assertRaises(UserError), self.env.cr.savepoint():
            proposal.action_confirm()
        self.assertEqual(self.rose.qty_available, 0)
        self.assertEqual(self.env["stock.scrap"].search_count(
            [("mgs_expiry_line_id", "=", proposal.line_ids.id)]), 1)

    def test_confirm_aborts_if_stock_changed_since_the_proposal(self):
        """Si algo movió el stock (una venta, un recuento) desde que se vio
        la propuesta, confirmar debe pararse, no dar de baja sobre datos viejos."""
        self.receive(10, days=-5)
        proposal = self.detect()
        # Se mueve el stock por otra vía después de generar la propuesta.
        scrap = self.env["stock.scrap"].create({
            "product_id": self.rose.id, "product_uom_id": self.rose.uom_id.id,
            "scrap_qty": 3, "lot_id": proposal.line_ids.lot_id.id,
            "location_id": proposal.line_ids.location_id.id, "mgs_reason": "deterioration",
        })
        scrap.do_scrap()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            proposal.action_confirm()
        self.assertEqual(proposal.state, "proposed")

    def test_cancelling_a_proposal_does_not_touch_stock(self):
        self.receive(10, days=-5)
        proposal = self.detect()
        proposal.action_cancel()
        self.assertEqual(proposal.state, "cancelled")
        self.assertEqual(self.rose.qty_available, 10)

    def test_only_the_owner_manages_expiry_writeoffs(self):
        self.receive(10, days=-5)
        proposal = self.detect()
        staff = new_test_user(
            self.env(context=dict(self.env.context, no_reset_password=True)),
            login="expiry_staff", groups="mi_gestor_stock.group_mgs_user")
        with self.assertRaises(Exception), self.env.cr.savepoint():
            proposal.with_user(staff).action_confirm()

    def test_stock_value_splits_usable_from_expired(self):
        self.receive(10, days=-5, cost=2.0)  # caducado
        self.receive(6, days=30, cost=3.0)   # vendible
        report = self.env["mgs.monthly.report"].create({
            "date_from": fields.Date.today(), "date_to": fields.Date.today()})
        data = report.mgs_get_report_data()
        self.assertEqual(data["stock_value"], 10 * 2.0 + 6 * 3.0)
        self.assertEqual(data["stock_value_expired"], 10 * 2.0)
        self.assertEqual(data["stock_value_usable"], 6 * 3.0)
