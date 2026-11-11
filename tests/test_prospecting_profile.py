# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from psycopg2.errors import NotNullViolation

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestProspectingProfile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env["prospecting.profile"]
        cls.product = cls.env["product.template"].create(
            {"name": "Test Service", "type": "service"}
        )
        cls.salesman = new_test_user(
            cls.env,
            login="prospecting_salesman",
            groups="sales_team.group_sale_salesman",
        )
        cls.manager = new_test_user(
            cls.env,
            login="prospecting_manager",
            groups="sales_team.group_sale_manager",
        )
        cls.profile = cls.Profile.create(
            {"name": "Existing profile", "product_id": cls.product.id}
        )

    def test_create_profile(self):
        profile = self.Profile.create(
            {
                "name": "Retail",
                "product_id": self.product.id,
                "icp": "First item\nSecond item",
                "buying_signals": "Signal one\nSignal two",
            }
        )
        self.assertEqual(profile.name, "Retail")
        self.assertEqual(profile.product_id, self.product)
        self.assertEqual(profile.icp.splitlines(), ["First item", "Second item"])
        self.assertEqual(
            profile.buying_signals.splitlines(), ["Signal one", "Signal two"]
        )
        self.assertTrue(profile.active, "A new profile is active by default")

    def test_archive_profile(self):
        self.profile.action_archive()
        self.assertFalse(self.profile.active)
        self.assertNotIn(
            self.profile, self.Profile.search([("name", "=", "Existing profile")])
        )

    def test_product_is_required(self):
        self.assertTrue(self.Profile._fields["product_id"].required)
        with mute_logger("odoo.sql_db"), self.assertRaises(NotNullViolation):
            self.Profile.create({"name": "No product"})
            self.env.flush_all()

    def test_name_is_required(self):
        self.assertTrue(self.Profile._fields["name"].required)
        with mute_logger("odoo.sql_db"), self.assertRaises(NotNullViolation):
            self.Profile.create({"product_id": self.product.id})
            self.env.flush_all()

    def test_salesman_can_read(self):
        profile = self.profile.with_user(self.salesman)
        self.assertEqual(profile.read(["name"])[0]["name"], "Existing profile")
        self.assertIn(profile, self.Profile.with_user(self.salesman).search([]))

    def test_salesman_cannot_create(self):
        with self.assertRaises(AccessError):
            self.Profile.with_user(self.salesman).create(
                {"name": "Forbidden", "product_id": self.product.id}
            )
        self.assertFalse(self.Profile.search([("name", "=", "Forbidden")]))

    def test_salesman_cannot_write(self):
        with self.assertRaises(AccessError):
            self.profile.with_user(self.salesman).write({"name": "Changed"})
        self.assertEqual(self.profile.name, "Existing profile")

    def test_salesman_cannot_unlink(self):
        with self.assertRaises(AccessError):
            self.profile.with_user(self.salesman).unlink()
        self.assertTrue(self.profile.exists())

    def test_manager_full_access(self):
        Profile = self.Profile.with_user(self.manager)
        profile = Profile.create({"name": "Managed", "product_id": self.product.id})
        self.assertEqual(Profile.search([("name", "=", "Managed")]), profile)
        profile.write({"icp": "Updated"})
        self.assertEqual(profile.icp, "Updated")
        profile.unlink()
        self.assertFalse(profile.exists())

    def test_internal_user_without_sales_group_has_no_access(self):
        user = new_test_user(
            self.env, login="prospecting_internal", groups="base.group_user"
        )
        with self.assertRaises(AccessError):
            self.profile.with_user(user).read(["name"])
