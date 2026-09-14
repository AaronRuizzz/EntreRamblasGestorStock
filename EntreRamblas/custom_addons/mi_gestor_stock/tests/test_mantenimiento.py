# -*- coding: utf-8 -*-
"""Hallazgo 11: `mgs.maintenance` lo escribe y lo borra el actualizador
alrededor de aplicar una actualización, pero ningún código de la aplicación lo
consultaba — no bloqueaba nada. Con el parámetro puesto, ninguna operación de
negocio (recepción, venta) debe poder completarse; sin él, deben funcionar con
normalidad."""
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..models.mgs_permissions import MAINTENANCE_PARAM


@tagged("post_install", "-at_install")
class TestMaintenanceBlocksBusinessWrites(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create({
            "name": "Rosa prueba mantenimiento", "is_storable": True,
            "tracking": "lot", "use_expiration_date": True,
        })

    def _set_maintenance(self, on):
        icp = self.env["ir.config_parameter"].sudo()
        if on:
            icp.set_param(MAINTENANCE_PARAM, fields.Datetime.now())
        else:
            icp.set_param(MAINTENANCE_PARAM, False)

    def _receive(self):
        wizard = self.env["mgs.reception"].create({
            "line_ids": [Command.create({
                "product_id": self.product.id, "quantity": 5, "unit_cost": 1,
                "expiry_date": fields.Date.today() + timedelta(days=5),
            })],
        })
        return wizard.action_confirm()

    def test_reception_is_blocked_during_maintenance_and_works_without_it(self):
        self._set_maintenance(True)
        with self.assertRaises(UserError):
            self._receive()
        self.assertFalse(self.product.qty_available)

        self._set_maintenance(False)
        self._receive()
        self.assertEqual(self.product.qty_available, 5)

    def test_pos_check_stock_is_blocked_during_maintenance(self):
        self._set_maintenance(True)
        with self.assertRaises(UserError):
            # session_id inventado: assert_not_maintenance corta ANTES de
            # llegar a validar la sesión.
            self.env["pos.order"].mgs_check_stock(999999, [])

        self._set_maintenance(False)
        # Sin sesión real la llamada sigue fallando, pero por otro motivo (no
        # por mantenimiento): demuestra que el corte ya no está activo.
        with self.assertRaises(UserError) as caught:
            self.env["pos.order"].mgs_check_stock(999999, [])
        self.assertNotIn("actualizando", str(caught.exception))

    def test_a_manager_operation_is_also_blocked(self):
        # require_manager()/require_operator() cubren el resto de escrituras
        # de negocio del módulo (eventos, ramos, importación, copias...).
        from ..models.mgs_permissions import require_manager
        self._set_maintenance(True)
        with self.assertRaises(UserError):
            require_manager(self.env(su=True))
        self._set_maintenance(False)
        require_manager(self.env(su=True))  # no lanza
