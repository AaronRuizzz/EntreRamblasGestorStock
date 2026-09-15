# -*- coding: utf-8 -*-
"""Una sola lista de categorías para el almacén y para la caja.

La dueña solo escribe la categoría al dar de alta el producto (Recepción →
«Producto nuevo»); el botón del TPV lo pone el módulo. Lo que se comprueba
aquí es justo eso: que no hay una segunda lista que mantener a mano y que lo
que se ve en la caja es lo que hay en el almacén.
"""
from odoo.tests import TransactionCase, tagged
from odoo.addons.point_of_sale.tests.common import TestPointOfSaleCommon
from odoo.addons.mi_gestor_stock.models.product_category import FACTORY_CATEGORIES


@tagged("post_install", "-at_install")
class TestPosCategoryMirror(TransactionCase):
    def setUp(self):
        super().setUp()
        # La base de la tienda puede llegar aquí con una caja abierta (una
        # venta a medias del día). Con la caja abierta, Odoo no deja retirar
        # categorías del TPV y el espejo aplaza las bajas a propósito — eso se
        # prueba aparte, en TestPosCategoryMirrorWithOpenTill. Este bloque
        # comprueba el camino normal, con la caja cerrada. La transacción de la
        # prueba se deshace al acabar: la sesión real no se toca.
        # `sudo()`: el espejo también mira con sudo, y una sesión de otro
        # usuario cuenta igual para Odoo a la hora de no dejar borrar.
        self.env["pos.session"].sudo().search(
            [("state", "!=", "closed")]).write({"state": "closed"})

    def categ(self, name, parent=None):
        return self.env["product.category"].create({
            "name": name, "parent_id": parent.id if parent else False,
        })

    def product(self, name, categ):
        return self.env["product.template"].create({"name": name, "categ_id": categ.id})

    # ------------------------------------------------------------------
    # Alta
    # ------------------------------------------------------------------
    def test_a_new_category_gets_its_button_in_the_pos(self):
        categ = self.categ("Ramos de novia")
        self.assertTrue(categ.mgs_pos_categ_id)
        self.assertEqual(categ.mgs_pos_categ_id.name, "Ramos de novia")

    def test_a_product_sells_under_the_button_of_its_stock_category(self):
        categ = self.categ("Plantas de interior")
        tmpl = self.product("Ficus", categ)
        self.assertEqual(tmpl.pos_categ_ids, categ.mgs_pos_categ_id)

    def test_moving_a_product_to_another_category_moves_its_button(self):
        origin, destination = self.categ("Flor cortada"), self.categ("Planta")
        tmpl = self.product("Gerbera", origin)
        tmpl.categ_id = destination
        self.assertEqual(tmpl.pos_categ_ids, destination.mgs_pos_categ_id)

    def test_a_child_category_hangs_from_its_parent_in_the_pos_too(self):
        parent = self.categ("Flores")
        child = self.categ("Rosas", parent=parent)
        self.assertEqual(child.mgs_pos_categ_id.parent_id, parent.mgs_pos_categ_id)

    # ------------------------------------------------------------------
    # Cambios posteriores
    # ------------------------------------------------------------------
    def test_renaming_a_category_renames_the_button(self):
        categ = self.categ("Centros")
        categ.name = "Centros de mesa"
        self.assertEqual(categ.mgs_pos_categ_id.name, "Centros de mesa")

    def test_archiving_a_category_takes_its_button_out_of_the_pos(self):
        categ = self.categ("Temporada")
        tmpl = self.product("Poinsettia", categ)
        mirror = categ.mgs_pos_categ_id
        categ.active = False
        self.assertFalse(mirror.exists())
        self.assertFalse(categ.mgs_pos_categ_id)
        # El producto no desaparece de la caja: se queda sin botón, en la
        # parrilla general.
        self.assertFalse(tmpl.pos_categ_ids)

    def test_unarchiving_a_category_brings_its_button_and_products_back(self):
        categ = self.categ("Temporada")
        tmpl = self.product("Poinsettia", categ)
        categ.active = False
        categ.active = True
        self.assertTrue(categ.mgs_pos_categ_id)
        self.assertEqual(tmpl.pos_categ_ids, categ.mgs_pos_categ_id)

    def test_deleting_a_category_deletes_its_button(self):
        categ = self.categ("Se borra")
        mirror = categ.mgs_pos_categ_id
        categ.unlink()
        self.assertFalse(mirror.exists())

    # ------------------------------------------------------------------
    # Repaso completo (data/ux_defaults.xml, en cada `-u`)
    # ------------------------------------------------------------------
    def test_the_factory_categories_are_archived_and_get_no_button(self):
        # «Todo», «Todo/Vendible», «Todo/Gastos» y «Todo/TPV» no significan
        # nada en la tienda: se archivan en cada `-u` y no ocupan un botón en
        # la pantalla de venta. Sin esto, el TPV enseñaba un botón «All» con el
        # catálogo entero dentro, que es justo lo contrario de agrupar.
        # Lo mismo que hace data/ux_defaults.xml en cada `-u`, en ese orden.
        self.env["product.category"]._mgs_archive_factory_categories()
        self.env["product.category"]._mgs_sync_all_pos_categories()
        for xmlid in FACTORY_CATEGORIES:
            categ = self.env.ref(xmlid, raise_if_not_found=False)
            if categ:
                self.assertFalse(categ.active, xmlid)
                self.assertFalse(categ.mgs_pos_categ_id, xmlid)

    def test_the_full_sync_repairs_a_category_left_without_a_button(self):
        # Una base que venía de antes del espejo: categorías y productos ya
        # creados, ningún botón en la caja.
        categ = self.categ("Herencia")
        tmpl = self.product("Hortensia", categ)
        categ.mgs_pos_categ_id.unlink()
        self.assertFalse(tmpl.pos_categ_ids)

        self.env["product.category"]._mgs_sync_all_pos_categories()

        self.assertTrue(categ.mgs_pos_categ_id)
        self.assertEqual(tmpl.pos_categ_ids, categ.mgs_pos_categ_id)

    def test_the_full_sync_does_not_duplicate_anything_when_run_twice(self):
        self.categ("Complementos")
        self.env["product.category"]._mgs_sync_all_pos_categories()
        before = self.env["pos.category"].search([]).ids
        self.env["product.category"]._mgs_sync_all_pos_categories()
        self.assertEqual(self.env["pos.category"].search([]).ids, before)

    def test_an_existing_button_with_the_same_name_is_adopted_instead_of_duplicated(self):
        # Un botón creado a mano (o por un escenario de ejemplo del TPV) con el
        # mismo nombre: se reutiliza, no se deja la caja con dos iguales.
        loose = self.env["pos.category"].create({"name": "Velas"})
        categ = self.categ("Velas")
        self.assertEqual(categ.mgs_pos_categ_id, loose)
        self.assertEqual(self.env["pos.category"].search_count([("name", "=", "Velas")]), 1)

    def test_two_categories_with_the_same_name_get_one_button_each(self):
        first = self.categ("Repetida")
        second = self.categ("Repetida")
        self.assertTrue(second.mgs_pos_categ_id)
        self.assertNotEqual(first.mgs_pos_categ_id, second.mgs_pos_categ_id)


@tagged("post_install", "-at_install")
class TestPosCategoryMirrorWithOpenTill(TestPointOfSaleCommon):
    """Con una venta a medias, la caja tiene las categorías cargadas y Odoo no
    deja borrarlas. Archivar una categoría no puede reventar por eso: ni al
    hacerlo a mano, ni —sobre todo— durante la actualización del módulo, que es
    cuando se archivan las de fábrica."""

    def test_archiving_with_the_till_open_defers_the_removal_instead_of_failing(self):
        categ = self.env["product.category"].create({"name": "Con caja abierta"})
        mirror = categ.mgs_pos_categ_id
        self.env["pos.session"].create({"config_id": self.pos_config.id})

        categ.active = False        # no levanta nada: la venta manda

        self.assertTrue(mirror.exists())
        self.assertEqual(categ.mgs_pos_categ_id, mirror)

    def test_the_deferred_removal_happens_on_the_next_update(self):
        categ = self.env["product.category"].create({"name": "Se retira luego"})
        mirror = categ.mgs_pos_categ_id
        session = self.env["pos.session"].create({"config_id": self.pos_config.id})
        categ.active = False

        # Cerrada la caja, el repaso completo de cada `-u` termina el trabajo.
        # (Se cierran todas: la base de la tienda puede traer alguna abierta
        # de un día anterior, y basta una para que la baja siga aplazada.)
        session.state = "closed"
        self.env["pos.session"].sudo().search(
            [("state", "!=", "closed")]).write({"state": "closed"})
        self.env["product.category"]._mgs_sync_all_pos_categories()

        self.assertFalse(mirror.exists())
        self.assertFalse(categ.mgs_pos_categ_id)
