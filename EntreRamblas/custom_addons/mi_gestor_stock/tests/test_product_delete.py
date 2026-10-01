# -*- coding: utf-8 -*-
"""«Eliminar» un producto: si ya tiene historial (movimientos de stock,
ventas...) la base no deja borrarlo — «violates RESTRICT setting of foreign
key constraint stock_move_product_id_fkey» — y se archiva en su lugar. Sin
historial se borra de verdad."""
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProductDelete(TransactionCase):
    def _product(self, name, with_history):
        product = self.env["product.product"].create({"name": name, "is_storable": True})
        if with_history:
            self.env["stock.move"].create({
                "name": name, "product_id": product.id, "product_uom_qty": 1.0,
                "product_uom": product.uom_id.id,
                "location_id": self.env.ref("stock.stock_location_suppliers").id,
                "location_dest_id": self.env.ref("stock.stock_location_stock").id,
            })
        return product

    def test_product_without_history_is_really_deleted(self):
        product = self._product("Sin historial", with_history=False)
        template = product.product_tmpl_id
        template.unlink()
        self.assertFalse(template.exists())
        self.assertFalse(product.exists())

    def test_template_with_stock_moves_is_archived_instead(self):
        product = self._product("Con historial", with_history=True)
        template = product.product_tmpl_id
        template.unlink()  # antes: error de clave ajena
        self.assertTrue(template.exists())
        self.assertFalse(template.active)
        self.assertFalse(product.active)

    def test_variant_with_stock_moves_archives_its_product(self):
        product = self._product("Variante con historial", with_history=True)
        product.unlink()
        self.assertTrue(product.exists())
        self.assertFalse(product.active)
        self.assertFalse(product.product_tmpl_id.active)

    def test_mixed_selection_deletes_what_it_can_and_archives_the_rest(self):
        free = self._product("Libre", with_history=False).product_tmpl_id
        used = self._product("Usado", with_history=True).product_tmpl_id
        (free | used).unlink()
        self.assertFalse(free.exists())
        self.assertTrue(used.exists())
        self.assertFalse(used.active)
