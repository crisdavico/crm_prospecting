# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.tests import TransactionCase, new_test_user, tagged

MENU_XMLIDS = (
    "crm_prospecting.prospecting_menu_root",
    "crm_prospecting.prospecting_campaign_menu",
    "crm_prospecting.prospecting_profile_menu",
)


@tagged("post_install", "-at_install")
class TestProspectingMenus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menus = cls.env["ir.ui.menu"]
        for xmlid in MENU_XMLIDS:
            cls.menus |= cls.env.ref(xmlid)
        cls.root = cls.env.ref("crm_prospecting.prospecting_menu_root")

    def _loaded_menu_ids(self, user):
        return set(self.env["ir.ui.menu"].with_user(user).load_menus(debug=False))

    def test_menu_tree(self):
        self.assertEqual(self.root.parent_id, self.env.ref("crm.crm_menu_root"))
        self.assertEqual(
            self.env.ref("crm_prospecting.prospecting_profile_menu").parent_id,
            self.root,
        )
        self.assertEqual(
            self.env.ref("crm_prospecting.prospecting_campaign_menu").parent_id,
            self.root,
        )
        self.assertEqual(self.root.child_id, self.menus - self.root)

    def test_salesman_sees_prospecting_menus(self):
        salesman = new_test_user(
            self.env,
            login="prospecting_menu_salesman",
            groups="sales_team.group_sale_salesman",
        )
        self.assertLessEqual(set(self.menus.ids), self._loaded_menu_ids(salesman))

    def test_internal_user_does_not_see_prospecting_menus(self):
        user = new_test_user(
            self.env, login="prospecting_menu_internal", groups="base.group_user"
        )
        self.assertFalse(set(self.menus.ids) & self._loaded_menu_ids(user))
