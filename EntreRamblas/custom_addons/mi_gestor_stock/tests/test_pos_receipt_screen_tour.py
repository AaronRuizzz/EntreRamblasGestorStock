# -*- coding: utf-8 -*-
"""Regresión: la pantalla de recibo del TPV (point_of_sale.ReceiptScreen) se
quedaba en blanco al completar una venta, tras recortar el bloque de envío
de ticket por email/SMS con un t-inherit por XPath. El fallo ocurría solo al
renderizar la plantilla de verdad en el navegador — test_pos_receipt.py ya
documenta que un chequeo estático de XPath (que sí detecta si el XPath no
CASA con nada) no detecta este tipo de fallo, porque el XPath casaba
correctamente y aun así el render fallaba. La solución (pos.scss: ocultar
por CSS sin tocar la plantilla, ver __manifest__.py) solo la valida de
verdad un tour de navegador que complete una venta real.

Este es el único test de la suite que ejecuta un tour real (HttpCase +
start_tour); necesita Chrome instalado (test.ps1 lo detecta solo en
%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe) y el paquete
`websocket-client` en el venv (si falta, el test se SALTA en silencio —
"websocket-client module is not installed" — en vez de fallar; revisar el
log si "0 failed, 0 error(s)" viene con "of 0 tests")."""
from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon


@tagged("post_install", "-at_install")
class TestReceiptScreenTour(TestPointOfSaleCommon, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        # Producto real de esta tienda: con lote automático (para la
        # caducidad) — el mismo tipo de producto que crea Recepción, y el
        # que exige el fix de agrupación (pos_hardware.js: isLotTracked).
        cls.flower = cls.env["product.product"].create({
            "name": "Rosa TPV", "tracking": "lot", "mgs_auto_lots": True,
            "is_storable": True, "available_in_pos": True, "sale_ok": True,
            "list_price": 5.0, "taxes_id": [Command.clear()],
        })
        cls.env["mgs.reception"].create({"line_ids": [Command.create({
            "product_id": cls.flower.id, "quantity": 10, "unit_cost": 1.0,
            "expiry_date": fields.Date.today() + timedelta(days=15),
        })]}).action_confirm()

        # Usuaria de pruebas con login/contraseña iguales a propósito:
        # HttpCase.start_tour(login=...) autentica con authenticate(login,
        # login) — ver odoo/tests/common.py:browser_js. group_mgs_user
        # evita que require_operator() (mgs_permissions.py) bloquee la
        # apertura del cajón al cobrar en efectivo, que no tiene que ver
        # con lo que este test comprueba.
        cls.tour_user = cls.env["res.users"].create({
            "name": "Cajera de pruebas", "login": "mgs_tour_user",
            "password": "mgs_tour_user",
            "groups_id": [Command.set([
                cls.env.ref("base.group_user").id,
                cls.env.ref("point_of_sale.group_pos_user").id,
                cls.env.ref("stock.group_stock_user").id,
                cls.env.ref("mi_gestor_stock.group_mgs_user").id,
            ])],
        })

    def test_receipt_screen_shows_after_cash_and_card_sales(self):
        # Sesión abierta por el servidor antes de arrancar el tour: evita
        # que el tour dependa de la interfaz de apertura de caja variando
        # con la configuración (aun así, como hay un método de pago en
        # efectivo, cash_control sigue exigiendo confirmar el "Control de
        # apertura" en el navegador — el propio tour lo hace).
        self.pos_config.with_user(self.tour_user).open_ui()
        session = self.pos_config.current_session_id

        self.start_tour(
            f"/pos/ui?config_id={self.pos_config.id}",
            "mgs_receipt_screen_after_payment",
            login=self.tour_user.login,
        )

        orders = self.env["pos.order"].search([("session_id", "=", session.id)])
        self.assertEqual(len(orders), 2,
                          "deberían quedar exactamente 2 ventas guardadas (efectivo + tarjeta)")
        self.assertEqual(set(orders.mapped("state")), {"paid"},
                          "las dos ventas deben quedar registradas como pagadas")
        self.assertEqual(len(set(orders.mapped("uuid"))), 2,
                          "cada venta debe tener su propio uuid: no se duplica al recargar")
        # La primera venta (efectivo) agrupó las dos pulsaciones del mismo
        # producto en una sola línea con cantidad 2 (regresión de
        # agrupación, ver pos_hardware.js:isLotTracked).
        cash_order = orders.filtered(
            lambda o: o.payment_ids.payment_method_id == self.cash_payment_method)
        self.assertEqual(len(cash_order.lines), 1,
                          "las dos pulsaciones del mismo producto deben quedar en una sola línea")
        self.assertEqual(cash_order.lines.qty, 2.0)
