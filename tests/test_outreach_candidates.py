# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestOutreachCandidates(TransactionCase):
    """`prospecting_outreach_candidates`: who the email agent may write to."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot = new_test_user(
            cls.env,
            "candidates_assistant",
            name="Candidates Assistant",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.Lead = cls.env["crm.lead"].with_user(cls.bot)
        Campaign = cls.env["utm.campaign"]
        cls.campaign = Campaign.create(
            {
                "title": "Outreach test",
                "prospecting_email_guidelines": "Write in Spanish.",
            }
        )
        cls.other_campaign = Campaign.create({"title": "Other campaign"})
        Stage = cls.env["crm.stage"]
        cls.first_stage = cls.env["crm.lead"]._stage_find()
        cls.later_stage = Stage.create({"name": "Proposal sent", "sequence": 50})
        cls.won_stage = Stage.create({"name": "Signed", "sequence": 60, "is_won": True})

    def _lead(self, company, contact, email, campaign=None, **vals):
        return self.env["crm.lead"].create(
            {
                "name": f"{company} - {contact}",
                "type": "lead",
                "partner_name": company,
                "contact_name": contact,
                "email_from": email,
                "campaign_id": (campaign or self.campaign).id,
                **vals,
            }
        )

    def _candidates(self, limit=10, user=None):
        Lead = self.env["crm.lead"].with_user(user) if user else self.Lead
        return Lead.prospecting_outreach_candidates(self.campaign.id, limit)

    def _lead_ids(self, result):
        return {
            person["lead_id"]
            for company in result["companies"]
            for person in company["people"]
        }

    # Eligible leads

    def test_eligible_lead_is_returned_with_only_what_picking_needs(self):
        lead = self._lead(
            "Acme",
            "Agustín Pérez",
            "agustin@acme.example",
            function="CTO",
            prospecting_fit_score=80,
        )
        result = self._candidates()
        self.assertEqual(
            result["companies"],
            [
                {
                    "name": "Acme",
                    "people": [
                        {
                            "lead_id": lead.id,
                            "name": "Agustín Pérez",
                            "job_title": "CTO",
                            "fit_score": 80,
                            "shared_inbox": False,
                        }
                    ],
                }
            ],
        )

    def test_people_of_one_company_are_grouped(self):
        cto = self._lead("Acme", "Ana", "ana@acme.example", prospecting_fit_score=50)
        ceo = self._lead("ACME ", "Beto", "beto@acme.example", prospecting_fit_score=90)
        result = self._candidates()
        self.assertEqual(len(result["companies"]), 1)
        people = result["companies"][0]["people"]
        self.assertEqual([p["lead_id"] for p in people], [ceo.id, cto.id])

    # Lead rules (D8)

    def test_inactive_lead_is_skipped(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example", active=False)
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_leads"]["inactive"], 1)

    def test_lead_without_email_is_skipped(self):
        lead = self._lead("Acme", "Ana", False)
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_leads"]["no_email"], 1)

    def test_blacklisted_lead_is_skipped(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example")
        self.env["mail.blacklist"].create({"email": "ana@acme.example"})
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_leads"]["blacklisted"], 1)

    def test_address_taken_off_the_blacklist_is_offered(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example")
        self.env["mail.blacklist"].create(
            {"email": "ana@acme.example", "active": False}
        )
        result = self._candidates()
        self.assertIn(lead.id, self._lead_ids(result))
        self.assertNotIn("blacklisted", result["skipped_leads"])

    def test_already_emailed_lead_is_skipped(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example")
        lead.prospecting_outreach_date = fields.Datetime.now()
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_leads"]["already_emailed"], 1)

    def test_campaign_without_guidelines_offers_nobody(self):
        self._lead("Acme", "Ana", "ana@acme.example")
        self._lead("Initech", "Beto", "beto@initech.example")
        self.campaign.prospecting_email_guidelines = "  \n"
        result = self._candidates()
        self.assertEqual(result["companies"], [])
        self.assertEqual(result["skipped_leads"], {"campaign_without_guidelines": 2})

    # Company rules (D10, D11)

    def test_company_already_emailed_in_another_campaign_is_skipped(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example", website="acme.example")
        self._lead(
            "Acme S.A.",
            "Beto",
            "beto@acme.example",
            campaign=self.other_campaign,
            website="https://www.acme.example/",
            prospecting_outreach_date=fields.Datetime.now(),
            active=False,
        )
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_companies"]["already_emailed"], 1)

    def test_company_with_an_opportunity_past_the_first_stage_is_skipped(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example", prospecting_cuit="30-1")
        self._lead(
            "Acme Holding",
            "Beto",
            "beto@acme.example",
            campaign=self.other_campaign,
            prospecting_cuit="301",
            type="opportunity",
            stage_id=self.later_stage.id,
        )
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_companies"]["opportunity_in_progress"], 1)

    def test_company_with_a_lost_opportunity_past_the_first_stage_is_offered(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example")
        self._lead(
            "Acme",
            "Beto",
            "beto@acme.example",
            campaign=self.other_campaign,
            type="opportunity",
            stage_id=self.later_stage.id,
            active=False,
        )
        result = self._candidates()
        self.assertIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_companies"], {})

    def test_company_with_a_first_stage_opportunity_is_offered(self):
        lead = self._lead(
            "Acme",
            "Ana",
            "ana@acme.example",
            type="opportunity",
            stage_id=self.first_stage.id,
        )
        self.assertIn(lead.id, self._lead_ids(self._candidates()))

    def test_won_company_is_skipped(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example")
        self._lead(
            "Acme",
            "Beto",
            "beto@acme.example",
            campaign=self.other_campaign,
            type="opportunity",
            stage_id=self.won_stage.id,
        )
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_companies"]["won"], 1)

    def test_company_keys_match_transitively(self):
        lead = self._lead("Acme", "Ana", "ana@acme.example", prospecting_cuit="30-7")
        # Shares the CUIT with Ana's lead and the website with the emailed lead.
        self._lead(
            "Acme Argentina",
            "Beto",
            False,
            campaign=self.other_campaign,
            prospecting_cuit="307",
            website="acme-ar.example",
        )
        self._lead(
            "ACM",
            "Carla",
            "carla@acme-ar.example",
            campaign=self.other_campaign,
            website="www.acme-ar.example",
            prospecting_outreach_date=fields.Datetime.now(),
        )
        result = self._candidates()
        self.assertNotIn(lead.id, self._lead_ids(result))
        self.assertEqual(result["skipped_companies"]["already_emailed"], 1)

    def test_shared_inbox_is_dropped_when_the_company_has_a_person(self):
        person = self._lead("Acme", "Ana", "ana@acme.example")
        inbox = self._lead("Acme", False, "info@acme.example")
        result = self._candidates()
        self.assertEqual(self._lead_ids(result), {person.id})
        self.assertNotIn(inbox.id, self._lead_ids(result))
        self.assertEqual(result["skipped_leads"]["shared_inbox"], 1)

    def test_shared_inbox_is_offered_when_the_company_has_no_one_else(self):
        inbox = self._lead("Initech", False, "ventas@initech.example")
        result = self._candidates()
        self.assertEqual(
            result["companies"][0]["people"],
            [
                {
                    "lead_id": inbox.id,
                    "name": "Initech",
                    "job_title": False,
                    "fit_score": 0,
                    "shared_inbox": True,
                }
            ],
        )

    # Limit (D6)

    def test_limit_counts_companies_best_fit_first(self):
        self._lead("Low", "Ana", "ana@low.example", prospecting_fit_score=10)
        self._lead("High", "Beto", "beto@high.example", prospecting_fit_score=90)
        self._lead("High", "Carla", "carla@high.example", prospecting_fit_score=20)
        self._lead("Mid", "Dora", "dora@mid.example", prospecting_fit_score=50)
        result = self._candidates(limit=2)
        self.assertEqual([c["name"] for c in result["companies"]], ["High", "Mid"])
        self.assertEqual(len(result["companies"][0]["people"]), 2)

    def test_limit_above_ten_or_below_one_is_refused(self):
        for limit in (0, 11, None, "5", 2.5, True):
            with self.subTest(limit=limit), self.assertRaises(UserError):
                self._candidates(limit=limit)

    # Access (D13)

    def test_only_leads_the_caller_can_read_are_returned(self):
        owner = new_test_user(
            self.env, "candidates_owner", groups="sales_team.group_sale_salesman"
        )
        other = new_test_user(
            self.env, "candidates_other", groups="sales_team.group_sale_salesman"
        )
        own = self._lead("Acme", "Ana", "ana@acme.example", user_id=owner.id)
        hidden = self._lead("Initech", "Beto", "beto@initech.example", user_id=other.id)
        result = self._candidates(user=owner)
        self.assertEqual(self._lead_ids(result), {own.id})
        self.assertNotIn(hidden.id, self._lead_ids(result))

    def test_a_company_blocked_by_an_unreadable_lead_is_still_blocked(self):
        owner = new_test_user(
            self.env, "candidates_owner2", groups="sales_team.group_sale_salesman"
        )
        other = new_test_user(
            self.env, "candidates_other2", groups="sales_team.group_sale_salesman"
        )
        self._lead("Acme", "Ana", "ana@acme.example", user_id=owner.id)
        self._lead(
            "Acme",
            "Beto",
            "beto@acme.example",
            user_id=other.id,
            prospecting_outreach_date=fields.Datetime.now(),
        )
        result = self._candidates(user=owner)
        self.assertEqual(result["companies"], [])
        self.assertEqual(result["skipped_companies"], {"already_emailed": 1})

    def test_unknown_campaign_is_refused(self):
        with self.assertRaises(UserError):
            self.Lead.prospecting_outreach_candidates(0, 10)
