# -*- coding: utf-8 -*-
"""Plantilla «Gestoría completa»: bloqueada de verdad, y solo ella puede
presentarse como informe para la gestoría."""
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.mgs_report_template import GESTORIA_XML_ID


@tagged("post_install", "-at_install")
class TestReportTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env, login="mgs_report_owner",
            groups="mi_gestor_stock.group_mgs_manager")
        cls.clerk = new_test_user(
            cls.env, login="mgs_report_clerk",
            groups="mi_gestor_stock.group_mgs_user")
        cls.gestoria = cls.env.ref(GESTORIA_XML_ID)
        cls.Template = cls.env["mgs.report.template"]

    def custom_template(self, **extra):
        vals = {"name": "Ventas de la vitrina de temporada"}
        vals.update(extra)
        return self.Template.with_user(self.owner).create(vals)

    # ------------------------------------------------------------------
    def test_manager_can_crud_a_custom_template(self):
        template = self.custom_template()
        self.assertTrue(template.section_ventas)
        template.with_user(self.owner).write({"name": "Ventas de primavera"})
        template.with_user(self.owner).unlink()

    def test_clerk_cannot_touch_templates(self):
        with self.assertRaises(AccessError):
            self.Template.with_user(self.clerk).create({"name": "Intento de dependienta"})
        template = self.custom_template()
        with self.assertRaises(AccessError):
            template.with_user(self.clerk).write({"name": "otro nombre"})

    def test_gestoria_is_locked_even_for_su(self):
        # Ni siquiera el superusuario puede tocar nada salvo el periodo.
        with self.assertRaises(AccessError):
            self.gestoria.sudo().write({"section_ventas": False})
        with self.assertRaises(AccessError):
            self.gestoria.sudo().write({"category_ids": [(4, self.env.ref("product.product_category_all").id)]})
        with self.assertRaises(AccessError):
            self.gestoria.with_user(self.owner).write({"name": "Renombrada"})
        # El periodo sí se puede ajustar cada mes.
        self.gestoria.with_user(self.owner).write({"date_from": "2026-01-01", "date_to": "2026-01-31"})
        self.assertEqual(str(self.gestoria.date_from), "2026-01-01")

    def test_gestoria_cannot_be_deleted_by_a_manager(self):
        with self.assertRaises(AccessError):
            self.gestoria.with_user(self.owner).unlink()

    def test_only_the_seeded_record_can_be_locked(self):
        # Ni siquiera la propietaria puede crear una segunda plantilla
        # bloqueada, y el sistema tampoco deja crear una segunda.
        with self.assertRaises(AccessError):
            self.custom_template(is_locked=True)
        with self.assertRaises(UserError):
            self.Template.sudo().create({"name": "Otra gestoría", "is_locked": True})

    def test_integrity_check_rejects_a_tampered_lock(self):
        self.gestoria.sudo()._mgs_check_gestoria_integrity()
        # Sortear write() con un UPDATE directo simula una edición fuera de la
        # app (o un bug futuro); _mgs_check_gestoria_integrity es la segunda
        # barrera que lo detecta en el momento de generar el informe.
        self.env.cr.execute(
            "UPDATE mgs_report_template SET section_ventas = false WHERE id = %s",
            [self.gestoria.id])
        self.gestoria.invalidate_recordset()
        with self.assertRaises(UserError):
            self.gestoria.sudo()._mgs_check_gestoria_integrity()

    def test_preview_starts_stale_and_refreshes_on_demand(self):
        template = self.custom_template()
        self.assertTrue(template.preview_stale)
        self.assertFalse(template.preview_generated_at)
        template.with_user(self.owner).action_refresh_preview()
        self.assertFalse(template.preview_stale)
        self.assertTrue(template.preview_generated_at)
        # Sin ventas en el periodo, la vista previa existe y está a cero: es
        # información («no hubo nada»), no un error.
        self.assertEqual(template.preview_sales_count, 0)

    def test_changing_a_filter_marks_the_preview_stale_again(self):
        template = self.custom_template()
        template.with_user(self.owner).action_refresh_preview()
        self.assertFalse(template.preview_stale)
        template.with_user(self.owner).write({"section_stock": False})
        self.assertTrue(template.preview_stale)

    def test_refreshing_the_locked_template_preview_does_not_trip_its_lock(self):
        # La vista previa la escribe el servidor, no la usuaria: el candado de
        # «Gestoría completa» no puede impedir que se actualice.
        self.gestoria.with_user(self.owner).action_refresh_preview()
        self.assertFalse(self.gestoria.preview_stale)

    def test_clerk_cannot_refresh_a_preview(self):
        template = self.custom_template()
        with self.assertRaises(AccessError):
            template.with_user(self.clerk).action_refresh_preview()

    def test_only_the_locked_record_is_the_gestoria_master(self):
        self.assertTrue(self.gestoria.is_gestoria_master)
        # Una plantilla nueva sin filtros no se puede hacer pasar por ella:
        # la etiqueta depende de la identidad del registro, no de que los
        # filtros estén vacíos.
        empty_custom = self.custom_template()
        self.assertFalse(empty_custom.category_ids or empty_custom.product_ids or empty_custom.payment_method_ids)
        self.assertFalse(empty_custom.is_gestoria_master)
