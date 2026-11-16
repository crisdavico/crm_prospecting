# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestOutreachBrief(TransactionCase):
    """What the email agent reads to write: the campaign brief and one lead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot = new_test_user(
            cls.env,
            "brief_assistant",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        product = cls.env["product.template"].create(
            {"name": "Missed-call bot", "type": "service"}
        )
        cls.profile = cls.env["prospecting.profile"].create(
            {
                "name": "Clinics",
                "product_id": product.id,
                "description": "Clinics that lose patients to missed calls.",
                "icp": "Private clinics\n\n  Dental offices  \n",
                "buying_signals": "Hiring receptionists",
            }
        )
        cls.campaign = cls.env["utm.campaign"].create(
            {
                "title": "Clinics AR",
                "prospecting_profile_id": cls.profile.id,
                "prospecting_goal": "Book demos.",
                "prospecting_email_guidelines": "Spanish, tú, under 120 words.",
            }
        )
        cls.lead = cls.env["crm.lead"].create(
            {
                "name": "Clínica Sur - Ana",
                "partner_name": "Clínica Sur",
                "contact_name": "Ana Gómez",
                "function": "Directora",
                "email_from": "ana@clinicasur.example",
                "phone": "+54 11 5555 0000",
                "website": "https://clinicasur.example",
                "prospecting_linkedin": "https://linkedin.com/in/anagomez",
                "prospecting_fit_score": 85,
                "country_id": cls.env.ref("base.ar").id,
                "description": "<p>Hiring two receptionists.</p>"
                "<p>Opens Saturdays.</p>",
            }
        )

    # Brief (S6)

    def test_brief_has_the_profile_goal_and_guidelines(self):
        brief = (
            self.env["utm.campaign"]
            .with_user(self.bot)
            .prospecting_outreach_brief(self.campaign.id)
        )
        self.assertEqual(
            brief,
            {
                "campaign_id": self.campaign.id,
                "name": "Clinics AR",
                "goal": "Book demos.",
                "email_guidelines": "Spanish, tú, under 120 words.",
                "profile": {
                    "product": "Missed-call bot",
                    "description": "Clinics that lose patients to missed calls.",
                    "icp": ["Private clinics", "Dental offices"],
                    "buying_signals": ["Hiring receptionists"],
                },
            },
        )

    def test_brief_without_a_profile_says_so(self):
        self.campaign.prospecting_profile_id = False
        brief = self.env["utm.campaign"].prospecting_outreach_brief(self.campaign.id)
        self.assertIs(brief["profile"], False)

    def test_brief_without_guidelines_is_refused_clearly(self):
        self.campaign.prospecting_email_guidelines = " "
        with self.assertRaisesRegex(UserError, "no email guidelines"):
            self.env["utm.campaign"].prospecting_outreach_brief(self.campaign.id)

    def test_brief_of_an_unknown_campaign_is_refused(self):
        with self.assertRaises(UserError):
            self.env["utm.campaign"].prospecting_outreach_brief(0)

    # Lead detail (S5)

    def test_detail_has_only_what_the_draft_needs(self):
        detail = (
            self.env["crm.lead"]
            .with_user(self.bot)
            .prospecting_outreach_detail(self.lead.id)
        )
        self.assertEqual(
            detail,
            {
                "lead_id": self.lead.id,
                "contact_name": "Ana Gómez",
                "company_name": "Clínica Sur",
                "job_title": "Directora",
                "evidence": "Hiring two receptionists.\nOpens Saturdays.",
                "website": "https://clinicasur.example",
                "linkedin": "https://linkedin.com/in/anagomez",
                "country": "Argentina",
            },
        )

    def test_detail_of_a_lead_the_caller_cannot_read_is_refused(self):
        salesman = new_test_user(
            self.env, "brief_salesman", groups="sales_team.group_sale_salesman"
        )
        self.lead.user_id = self.bot
        with self.assertRaises(AccessError):
            self.env["crm.lead"].with_user(salesman).prospecting_outreach_detail(
                self.lead.id
            )

    def test_detail_of_an_unknown_lead_is_refused(self):
        with self.assertRaises(UserError):
            self.env["crm.lead"].prospecting_outreach_detail(0)
