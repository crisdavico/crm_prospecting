# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestProspectingStage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Stage = cls.env["utm.stage"]
        cls.open_stage = Stage.create(
            {"name": "Prospecting open", "prospecting_enabled": True}
        )
        cls.closed_stage = Stage.create({"name": "Prospecting closed"})
        Campaign = cls.env["utm.campaign"]
        cls.open_campaign = Campaign.create(
            {"title": "Stage test open", "stage_id": cls.open_stage.id}
        )
        cls.closed_campaign = Campaign.create(
            {"title": "Stage test closed", "stage_id": cls.closed_stage.id}
        )

    def test_flag_is_off_by_default(self):
        self.assertFalse(self.closed_stage.prospecting_enabled)

    def test_campaigns_filter_by_the_stage_flag(self):
        found = self.env["utm.campaign"].search(
            [
                ("id", "in", (self.open_campaign | self.closed_campaign).ids),
                ("stage_id.prospecting_enabled", "=", True),
            ]
        )
        self.assertEqual(found, self.open_campaign)

    def test_salesman_reads_the_flag(self):
        salesman = new_test_user(
            self.env,
            login="stage_flag_salesman",
            groups="sales_team.group_sale_salesman",
        )
        stage = self.open_stage.with_user(salesman)
        self.assertTrue(stage.prospecting_enabled)

    def test_stage_views_show_the_flag(self):
        Stage = self.env["utm.stage"]
        for view_type in ("list", "form"):
            arch = Stage.get_view(view_type=view_type)["arch"]
            self.assertIn('name="prospecting_enabled"', arch, view_type)
