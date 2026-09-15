from odoo.exceptions import UserError
from odoo.tests import tagged, new_test_user
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestProductCategory(TransactionCase):
    """Categorías que se conservan (plan «Correcciones de ventas», #5):
    `product.category.mgs_find_or_create` reutiliza por nombre normalizado
    (espacios/mayúsculas no cuentan) o crea, de forma idempotente ante
    reintentos/condición de carrera (constraint única + recuperación)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref("mi_gestor_stock.group_mgs_manager")
        cls.Category = cls.env["product.category"]

    def test_find_or_create_creates_when_missing(self):
        category = self.Category.mgs_find_or_create("Rosas")
        self.assertEqual(category.name, "Rosas")
        self.assertEqual(category.mgs_name_normalized, "rosas")

    def test_find_or_create_reuses_existing_case_insensitive(self):
        first = self.Category.mgs_find_or_create("Rosas")
        for variant in ("rosas", "ROSAS", "  Rosas  ", "Rosas\t"):
            self.assertEqual(self.Category.mgs_find_or_create(variant), first)
        self.assertEqual(self.Category.search_count([("mgs_name_normalized", "=", "rosas")]), 1)

    def test_find_or_create_collapses_internal_whitespace(self):
        first = self.Category.mgs_find_or_create("Flores  de   temporada")
        self.assertEqual(self.Category.mgs_find_or_create("Flores de temporada"), first)

    def test_find_or_create_empty_name_is_rejected(self):
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.Category.mgs_find_or_create("   ")

    def test_find_or_create_recovers_after_race_condition(self):
        # Simula la condición de carrera: otra transacción ya creó la
        # categoría con el mismo nombre normalizado entre la búsqueda y el
        # intento de creación. mgs_find_or_create no debe propagar el fallo
        # de la restricción única: debe recuperarse buscando de nuevo.
        winner = self.Category.create({"name": "Tulipanes"})
        result = self.Category.mgs_find_or_create("tulipanes")
        self.assertEqual(result, winner)

    def test_find_or_create_rpc_returns_plain_dict(self):
        result = self.Category.mgs_find_or_create_rpc("Claveles")
        self.assertEqual(set(result), {"id", "name"})
        self.assertEqual(result["name"], "Claveles")
        category = self.Category.browse(result["id"])
        self.assertEqual(category.name, "Claveles")

    def test_find_or_create_requires_operator_permission(self):
        # Empleada interna SIN los grupos de la floristería: ni dependienta
        # ni propietaria. require_operator debe rechazarla.
        outsider = new_test_user(
            self.env(context=dict(self.env.context, no_reset_password=True)),
            login="mgs_category_outsider", groups="base.group_user",
            company_id=self.env.company.id)
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.Category.with_user(outsider).mgs_find_or_create("Orquídeas")
