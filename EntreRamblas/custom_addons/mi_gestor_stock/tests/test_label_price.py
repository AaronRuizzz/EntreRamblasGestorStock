# -*- coding: utf-8 -*-
"""Precio de venta + IVA: el que se ve en la ficha del producto y el que
sale en la etiqueta del código de barras (mgs_config._mgs_print_labels).
Antes la etiqueta llevaba el precio SIN IVA."""
from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLabelPriceWithTax(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax21 = cls.env["account.tax"].create({
            "name": "IVA 21 (test etiqueta)", "amount": 21.0,
            "amount_type": "percent", "type_tax_use": "sale",
            "price_include_override": "tax_excluded",
        })
        cls.product = cls.env["product.product"].create({
            "name": "Rosa etiqueta", "is_storable": True, "list_price": 10.0,
            "barcode": "2000000000015", "taxes_id": [Command.set(cls.tax21.ids)],
        })
        cls.template = cls.product.product_tmpl_id

    def _printed_amounts(self, records):
        config = self.env["mgs.config"]._mgs_get()
        amounts = []

        def fake_amount(_self, amount, currency=None):
            amounts.append(amount)
            return "%.2f" % amount

        with patch.object(type(config), "_mgs_send"), \
             patch.object(type(config), "_mgs_amount", autospec=True, side_effect=fake_amount):
            config._mgs_print_labels(records, copies=1)
        return amounts

    def test_product_shows_the_sale_price_plus_vat(self):
        self.assertAlmostEqual(self.template.mgs_list_price_taxed, 12.10, places=2)

    def test_price_with_vat_follows_the_sale_price(self):
        self.template.list_price = 20.0
        self.assertAlmostEqual(self.template.mgs_list_price_taxed, 24.20, places=2)

    def test_without_taxes_it_is_the_sale_price(self):
        self.template.taxes_id = [Command.clear()]
        self.assertAlmostEqual(self.template.mgs_list_price_taxed, 10.0, places=2)

    def test_label_prints_the_price_with_vat(self):
        # Desde la ficha (product.template) y desde la recepción (product.product).
        self.assertEqual(self._printed_amounts(self.template), [12.10])
        self.assertEqual(self._printed_amounts(self.product), [12.10])
