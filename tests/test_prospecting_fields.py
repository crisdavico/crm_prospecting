# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProspectingFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.template"].create(
            {"name": "Test Service", "type": "service"}
        )
        cls.profile = cls.env["prospecting.profile"].create(
            {"name": "Test profile", "product_id": product.id}
        )
        cls.states = cls.env["res.country.state"].search(
            [("country_id.code", "=", "AR")], limit=2
        )
        cls.campaign = cls.env["utm.campaign"].create({"title": "Prospecting test"})

    def test_campaign_brief_round_trip(self):
        self.assertEqual(len(self.states), 2, "base ships Argentine states")
        self.campaign.write(
            {
                "prospecting_profile_id": self.profile.id,
                "prospecting_industry": "Auto parts",
                "prospecting_state_ids": [(6, 0, self.states.ids)],
                "prospecting_city": "Rosario",
                "prospecting_company_size": "10-50 employees",
                "prospecting_target_count": 25,
                "prospecting_instructions": "Skip current customers.",
            }
        )
        self.env.invalidate_all()
        campaign = self.env["utm.campaign"].browse(self.campaign.id)
        self.assertEqual(campaign.prospecting_profile_id, self.profile)
        self.assertEqual(campaign.prospecting_industry, "Auto parts")
        self.assertEqual(campaign.prospecting_state_ids, self.states)
        self.assertEqual(campaign.prospecting_city, "Rosario")
        self.assertEqual(campaign.prospecting_company_size, "10-50 employees")
        self.assertEqual(campaign.prospecting_target_count, 25)
        self.assertEqual(campaign.prospecting_instructions, "Skip current customers.")

    def test_lead_fields_round_trip(self):
        lead = self.env["crm.lead"].create(
            {
                "name": "Prospect",
                "campaign_id": self.campaign.id,
                "prospecting_fit_score": 80,
                "prospecting_evidence": "Job posting for collections.",
                "prospecting_cuit": "30-12345678-9",
                "prospecting_run_ref": "thread-123",
            }
        )
        self.env.invalidate_all()
        lead = self.env["crm.lead"].browse(lead.id)
        self.assertEqual(lead.campaign_id, self.campaign)
        self.assertEqual(lead.prospecting_fit_score, 80)
        self.assertEqual(lead.prospecting_evidence, "Job posting for collections.")
        self.assertEqual(lead.prospecting_cuit, "30-12345678-9")
        self.assertEqual(lead.prospecting_run_ref, "thread-123")
        self.assertEqual(
            self.env["crm.lead"].search([("prospecting_cuit", "=", "30-12345678-9")]),
            lead,
        )

    def test_fit_score_accepts_bounds(self):
        lead = self.env["crm.lead"].create({"name": "Bounds"})
        for score in (0, 100):
            lead.prospecting_fit_score = score
            self.assertEqual(lead.prospecting_fit_score, score)

    def test_fit_score_rejects_out_of_range(self):
        lead = self.env["crm.lead"].create(
            {"name": "Out of range", "prospecting_fit_score": 50}
        )
        for score in (-1, 101):
            with self.assertRaises(ValidationError):
                lead.write({"prospecting_fit_score": score})
            self.assertEqual(lead.prospecting_fit_score, 50)
        with self.assertRaises(ValidationError):
            self.env["crm.lead"].create(
                {"name": "Too high", "prospecting_fit_score": 101}
            )
        self.assertFalse(self.env["crm.lead"].search([("name", "=", "Too high")]))
