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
        cls.argentina = cls.env.ref("base.ar")
        cls.states = cls.env.ref("base.state_ar_b") | cls.env.ref("base.state_ar_c")
        cls.us_state = cls.env.ref("base.state_us_1")
        cls.industry = cls.env["res.partner.industry"].create({"name": "Auto parts"})
        cls.campaign = cls.env["utm.campaign"].create({"title": "Prospecting test"})

    def test_campaign_brief_round_trip(self):
        self.campaign.write(
            {
                "prospecting_profile_id": self.profile.id,
                "prospecting_industry_id": self.industry.id,
                "prospecting_country_id": self.argentina.id,
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
        self.assertEqual(campaign.prospecting_industry_id, self.industry)
        self.assertEqual(campaign.prospecting_country_id, self.argentina)
        self.assertEqual(campaign.prospecting_state_ids, self.states)
        self.assertEqual(campaign.prospecting_city, "Rosario")
        self.assertEqual(campaign.prospecting_company_size, "10-50 employees")
        self.assertEqual(campaign.prospecting_target_count, 25)
        self.assertEqual(campaign.prospecting_instructions, "Skip current customers.")

    def test_industry_is_the_partner_industry(self):
        field = self.env["utm.campaign"]._fields["prospecting_industry_id"]
        self.assertEqual(field.comodel_name, "res.partner.industry")
        self.assertEqual(
            field.comodel_name,
            self.env["res.partner"]._fields["industry_id"].comodel_name,
        )
        self.campaign.prospecting_industry_id = self.industry
        self.env.invalidate_all()
        self.assertEqual(
            self.env["utm.campaign"]
            .browse(self.campaign.id)
            .prospecting_industry_id.name,
            "Auto parts",
        )

    def test_country_round_trip_and_search(self):
        elsewhere = self.env["utm.campaign"].create(
            {
                "title": "Prospecting test elsewhere",
                "prospecting_country_id": self.env.ref("base.us").id,
            }
        )
        self.campaign.prospecting_country_id = self.argentina
        self.env.invalidate_all()
        # Limited to this test's campaigns: the database may hold others for the country.
        self.assertEqual(
            self.env["utm.campaign"].search(
                [
                    ("prospecting_country_id", "=", self.argentina.id),
                    ("id", "in", (self.campaign | elsewhere).ids),
                ]
            ),
            self.campaign,
        )

    def test_state_from_other_country_rejected(self):
        self.campaign.write(
            {
                "prospecting_country_id": self.argentina.id,
                "prospecting_state_ids": [(6, 0, self.states.ids)],
            }
        )
        with self.assertRaises(ValidationError):
            self.campaign.write({"prospecting_state_ids": [(4, self.us_state.id)]})
        with self.assertRaises(ValidationError):
            self.env["utm.campaign"].create(
                {
                    "title": "Mixed states",
                    "prospecting_country_id": self.argentina.id,
                    "prospecting_state_ids": [(6, 0, self.us_state.ids)],
                }
            )
        self.assertEqual(self.campaign.prospecting_state_ids, self.states)
        self.assertFalse(
            self.env["utm.campaign"].search([("title", "=", "Mixed states")])
        )

    def test_changing_country_away_from_states_rejected(self):
        self.campaign.write({"prospecting_state_ids": [(6, 0, self.states.ids)]})
        with self.assertRaises(ValidationError):
            self.campaign.write({"prospecting_country_id": self.env.ref("base.us").id})
        self.assertFalse(self.campaign.prospecting_country_id)

    def test_states_accepted_without_country(self):
        states = self.states | self.us_state
        self.campaign.write({"prospecting_state_ids": [(6, 0, states.ids)]})
        self.assertFalse(self.campaign.prospecting_country_id)
        self.assertEqual(self.campaign.prospecting_state_ids, states)

    def test_lead_fields_round_trip(self):
        lead = self.env["crm.lead"].create(
            {
                "name": "Prospect",
                "campaign_id": self.campaign.id,
                "prospecting_fit_score": 80,
                "prospecting_cuit": "30-12345678-9",
                "prospecting_run_ref": "thread-123",
            }
        )
        self.env.invalidate_all()
        lead = self.env["crm.lead"].browse(lead.id)
        self.assertEqual(lead.campaign_id, self.campaign)
        self.assertEqual(lead.prospecting_fit_score, 80)
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
