import json
from datetime import timedelta
from uuid import uuid4

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestStockDeficit(TestPointOfSaleCommon):
    """Venta con falta de stock (plan «Correcciones de ventas», #1).

    `mgs_check_stock` ya no bloquea por falta de existencias: devuelve la
    falta como dato (`deficits`). Confirmarla («Añadir de todos modos» en el
    TPV) pasa por `mgs_authorize_deficit`, que dejar constancia en
    `mgs.stock.deficit` de cuánto se ha autorizado a faltar para esa venta y
    ese producto. Al cobrar de verdad, `_mgs_reserve_available_lots` solo
    permite la venta en negativo si encuentra esa autorización; si no, sigue
    bloqueando como siempre (ver test_pos_stock.TestPosStock)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa déficit", "tracking": "lot", "mgs_auto_lots": True,
            "use_expiration_date": True, "is_storable": True, "taxes_id": [Command.clear()],
        })
        cls.session = cls.env["pos.session"].create({"config_id": cls.pos_config.id})
        cls.session.set_opening_control(0, "")

    def receive(self, quantity, cost, days, product=None):
        product = product or self.flower
        wizard = self.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": product.id, "quantity": quantity, "unit_cost": cost,
            "expiry_date": fields.Date.today() + timedelta(days=days),
        })]})
        wizard.action_confirm()
        return wizard.picking_id.move_line_ids.lot_id

    def order(self, quantity, product=None, uuid=None):
        product = product or self.flower
        return self.env["pos.order"].create({
            "uuid": uuid or str(uuid4()),
            "session_id": self.session.id, "amount_tax": 0,
            "amount_total": quantity * 10, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": product.id, "qty": quantity, "price_unit": 10,
                "price_subtotal": quantity * 10, "price_subtotal_incl": quantity * 10,
            })],
        })

    # ------------------------------------------------------------------
    # mgs_check_stock: devuelve deficits, no lanza excepción
    # ------------------------------------------------------------------
    def test_check_stock_zero_available_returns_deficit_not_raise(self):
        api = self.env["pos.order"]
        result = api.mgs_check_stock(self.session.id, [{"product_id": self.flower.id, "qty": 3}])
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["deficits"]), 1)
        self.assertEqual(result["deficits"][0]["available"], 0)
        self.assertEqual(result["deficits"][0]["missing"], 3)

    def test_check_stock_insufficient_partial_deficit(self):
        self.receive(2, 1, 5)
        api = self.env["pos.order"]
        result = api.mgs_check_stock(self.session.id, [{"product_id": self.flower.id, "qty": 5}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["deficits"][0]["missing"], 3)

    def test_check_stock_negative_balance_still_counts_as_zero_available(self):
        # Vender ya en negativo (partida pendiente de revisar) y volver a
        # comprobar: la disponibilidad no baja de 0 para el cálculo de falta.
        order = self.order(3)
        self.env["pos.order"].mgs_authorize_deficit(
            self.session.id, order.uuid, [{"product_id": self.flower.id, "qty": 3}])
        order._create_order_picking()
        self.assertEqual(self.flower.qty_available, -3)
        result = self.env["pos.order"].mgs_check_stock(
            self.session.id, [{"product_id": self.flower.id, "qty": 1}])
        self.assertFalse(result["ok"])
        self.assertEqual(result["deficits"][0]["available"], 0)
        self.assertEqual(result["deficits"][0]["missing"], 1)

    # ------------------------------------------------------------------
    # mgs_authorize_deficit: autorización por venta+producto
    # ------------------------------------------------------------------
    def test_authorize_deficit_then_check_ok(self):
        api = self.env["pos.order"]
        order = self.order(5)
        lines = [{"product_id": self.flower.id, "qty": 5}]
        result = api.mgs_authorize_deficit(self.session.id, order.uuid, lines)
        self.assertTrue(result["ok"])
        self.assertEqual(self.env["mgs.stock.deficit"].search_count([("order_uuid", "=", order.uuid)]), 1)
        notice = self.env["mgs.stock.alert.notice"].search([("pos_order_uuid", "=", order.uuid)])
        self.assertEqual(len(notice), 1)

    def test_authorize_deficit_increase_requires_reauthorization(self):
        # Aceptar una vez no habilita ventas posteriores: si la falta sube
        # después de aceptar, vuelve a pedir confirmación.
        api = self.env["pos.order"]
        order = self.order(2)
        api.mgs_authorize_deficit(self.session.id, order.uuid, [{"product_id": self.flower.id, "qty": 2}])
        result = api.mgs_check_stock(self.session.id, [{"product_id": self.flower.id, "qty": 5}], order.uuid)
        self.assertFalse(result["ok"])
        self.assertEqual(result["deficits"][0]["missing"], 5)
        self.assertEqual(result["deficits"][0]["authorized"], 2)
        # Autorizar la nueva cantidad sí lo cubre.
        result = api.mgs_authorize_deficit(self.session.id, order.uuid, [{"product_id": self.flower.id, "qty": 5}])
        self.assertTrue(result["ok"])

    def test_authorize_deficit_idempotent_retry(self):
        api = self.env["pos.order"]
        order = self.order(3)
        lines = [{"product_id": self.flower.id, "qty": 3}]
        api.mgs_authorize_deficit(self.session.id, order.uuid, lines)
        api.mgs_authorize_deficit(self.session.id, order.uuid, lines)
        api.mgs_authorize_deficit(self.session.id, order.uuid, lines)
        self.assertEqual(self.env["mgs.stock.deficit"].search_count([("order_uuid", "=", order.uuid)]), 1)
        self.assertEqual(
            self.env["mgs.stock.deficit"].search([("order_uuid", "=", order.uuid)]).authorized_qty, 3)

    # ------------------------------------------------------------------
    # Cobro real: partida "Pendiente de revisar"
    # ------------------------------------------------------------------
    def test_pay_with_negative_stock_creates_pending_review_lot(self):
        self.receive(2, 3, 5)
        api = self.env["pos.order"]
        order = self.order(5)
        api.mgs_authorize_deficit(self.session.id, order.uuid, [{"product_id": self.flower.id, "qty": 5}])
        order._create_order_picking()
        self.assertEqual(order.picking_ids.state, "done")
        self.assertEqual(self.flower.qty_available, -3)
        pending = self.env["stock.lot"].search([
            ("product_id", "=", self.flower.id), ("mgs_pending_review", "=", True)])
        self.assertEqual(len(pending), 1)
        pending_lines = order.picking_ids.move_line_ids.filtered(lambda ml: ml.lot_id == pending)
        self.assertEqual(sum(pending_lines.mapped("quantity")), 3)
        self.assertTrue(all(pending_lines.mapped("mgs_cost_estimated")))
        self.assertEqual(set(pending_lines.mapped("mgs_unit_cost")), {self.flower.standard_price})

    def test_pay_does_not_use_expired_lots_for_shortfall(self):
        expired = self.receive(5, 2, -1)  # ya caducada: no cuenta como disponible
        api = self.env["pos.order"]
        order = self.order(2)
        api.mgs_authorize_deficit(self.session.id, order.uuid, [{"product_id": self.flower.id, "qty": 2}])
        order._create_order_picking()
        # La partida caducada se queda intacta (5) en el almacén: no se toca,
        # aunque siga físicamente en el estante hasta que se merme. Lo
        # vendido sale de la partida "Pendiente de revisar" (-2), no de la
        # caducada.
        self.assertEqual(self.flower.qty_available, 3)
        pending = self.env["stock.lot"].search([
            ("product_id", "=", self.flower.id), ("mgs_pending_review", "=", True)])
        self.assertEqual(set(order.picking_ids.move_line_ids.mapped("lot_id")), {pending})
        expired_quant = self.env["stock.quant"].search([
            ("product_id", "=", self.flower.id), ("lot_id", "=", expired.id),
            ("location_id.usage", "=", "internal")])
        self.assertEqual(sum(expired_quant.mapped("quantity")), 5)

    def test_pending_review_lot_is_reused_across_sales(self):
        api = self.env["pos.order"]
        first = self.order(1)
        api.mgs_authorize_deficit(self.session.id, first.uuid, [{"product_id": self.flower.id, "qty": 1}])
        first._create_order_picking()
        second = self.order(1)
        api.mgs_authorize_deficit(self.session.id, second.uuid, [{"product_id": self.flower.id, "qty": 1}])
        second._create_order_picking()
        pending = self.env["stock.lot"].search([
            ("product_id", "=", self.flower.id), ("mgs_pending_review", "=", True)])
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.flower.qty_available, -2)

    def test_sale_without_authorization_still_blocks(self):
        # Sin pasar por mgs_authorize_deficit (p. ej. un pedido creado a
        # mano, como en test_pos_stock), la falta de stock sigue bloqueando.
        self.receive(1, 2, 5)
        order = self.order(3)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order._create_order_picking()

    def test_concurrent_authorize_deficit_same_session_no_duplicate(self):
        api = self.env["pos.order"]
        order = self.order(4)
        lines = [{"product_id": self.flower.id, "qty": 4}]
        for _ in range(3):
            api.mgs_authorize_deficit(self.session.id, order.uuid, lines)
        self.assertEqual(self.env["mgs.stock.deficit"].search_count([("order_uuid", "=", order.uuid)]), 1)

    def test_refund_of_exception_sale_restores_stock(self):
        self.receive(2, 3, 5)
        api = self.env["pos.order"]
        sale = self.order(5)
        api.mgs_authorize_deficit(self.session.id, sale.uuid, [{"product_id": self.flower.id, "qty": 5}])
        sale._create_order_picking()
        self.assertEqual(self.flower.qty_available, -3)
        refund = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id, "amount_tax": 0,
            "amount_total": -50, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": self.flower.id, "qty": -5, "price_unit": 10,
                "price_subtotal": -50, "price_subtotal_incl": -50,
                "refunded_orderline_id": sale.lines.id,
            })],
        })
        refund._create_order_picking()
        self.assertEqual(refund.picking_ids.state, "done")
        self.assertEqual(self.flower.qty_available, 2)

    # ------------------------------------------------------------------
    # Componentes de ramo (mgs_bouquet): la falta se expande al material
    # ------------------------------------------------------------------
    def test_bouquet_component_deficit_authorizes_and_pays(self):
        bouquet = self.env["product.product"].create({
            "name": "Ramo déficit", "is_storable": False, "type": "consu",
            "mgs_is_composition": True, "available_in_pos": True,
            "taxes_id": [Command.clear()], "list_price": 0.0,
        })
        self.receive(3, 2.0, 5)
        api = self.env["pos.order"]
        spec = json.dumps([{"product_id": self.flower.id, "qty": 7}])
        lines = [{"product_id": bouquet.id, "qty": 1, "bouquet_spec": spec}]
        order = self.env["pos.order"].create({
            "uuid": str(uuid4()), "session_id": self.session.id, "amount_tax": 0,
            "amount_total": 25.0, "amount_paid": 0, "amount_return": 0,
            "lines": [Command.create({
                "product_id": bouquet.id, "qty": 1, "price_unit": 25.0,
                "price_subtotal": 25.0, "price_subtotal_incl": 25.0,
                "mgs_bouquet_spec": spec,
            })],
        })
        result = api.mgs_check_stock(self.session.id, lines, order.uuid)
        self.assertFalse(result["ok"])
        self.assertEqual(result["deficits"][0]["product_id"], self.flower.id)
        self.assertEqual(result["deficits"][0]["missing"], 4)
        api.mgs_authorize_deficit(self.session.id, order.uuid, lines)
        order._create_order_picking()
        self.assertEqual(order.picking_ids.state, "done")
        self.assertEqual(self.flower.qty_available, -4)
        pending = self.env["stock.lot"].search([
            ("product_id", "=", self.flower.id), ("mgs_pending_review", "=", True)])
        self.assertTrue(pending)
