from unittest.mock import patch
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged, new_test_user
from ..models.mgs_permissions import is_manager


@tagged("post_install", "-at_install")
class TestSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = new_test_user(cls.env(context=dict(cls.env.context, no_reset_password=True)), login="mgs_staff", groups="mi_gestor_stock.group_mgs_user")
        cls.owner = new_test_user(cls.env(context=dict(cls.env.context, no_reset_password=True)), login="mgs_owner", groups="mi_gestor_stock.group_mgs_manager")
        cls.outsider = new_test_user(cls.env(context=dict(cls.env.context, no_reset_password=True)), login="mgs_other", groups="base.group_user")
        cls.product = cls.env["product.product"].create({"name": "Coste privado", "standard_price": 37})

    def test_staff_cannot_read_costs_or_open_management_wizards(self):
        self.assertFalse(is_manager(self.env(user=self.staff)))
        for model, record_id, field in [
            ("product.product", self.product.id, "standard_price"),
            ("product.template", self.product.product_tmpl_id.id, "standard_price"),
        ]:
            with self.assertRaises(AccessError):
                self.env[model].with_user(self.staff).browse(record_id).read([field])
        for model in ("mgs.reception", "mgs.monthly.report"):
            with self.assertRaises(AccessError):
                self.env[model].with_user(self.staff).create({})
        fields = self.env["product.product"].with_user(self.staff)._load_pos_data_fields(False)
        self.assertNotIn("standard_price", fields)
        self.assertEqual(self.product.with_user(self.owner).read(["standard_price"])[0]["standard_price"], 37)

    def test_public_methods_enforce_roles_before_side_effects(self):
        config = self.env["mgs.config"]._mgs_get()
        with patch.object(type(config), "_mgs_send") as send:
            for method in ("action_mgs_test_print", "action_mgs_open_drawer", "mgs_open_drawer", "action_mgs_backup_now"):
                with self.assertRaises(AccessError):
                    getattr(config.with_user(self.staff), method)()
            with self.assertRaises(AccessError):
                self.env["mgs.config"].with_user(self.outsider).mgs_pos_hardware_info()
            with self.assertRaises(AccessError):
                self.env["mgs.config"].with_user(self.outsider).mgs_pos_open_drawer()
            send.assert_not_called()
        report = self.env["mgs.monthly.report"].create({})
        with self.assertRaises(AccessError):
            report.with_user(self.staff).mgs_get_report_data()

    def test_staff_cannot_apply_inventory_adjustments(self):
        with self.assertRaises(AccessError):
            self.env["stock.quant"].with_user(self.staff)._apply_inventory()
