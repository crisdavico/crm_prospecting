# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.tests import new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.tests.common import MailCase

CUSTOMER_EMAIL = "agustin.perez@acme.example"

# An email answering the agent's first email, as the mail gateway receives it.
REPLY_TEMPLATE = """Return-Path: {return_path}
To: {to}
Received: by mx.acme.example
Message-ID: {msg_id}
Date: {date}
Subject: {subject}
From: {email_from}
{extra}MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: 8bit

Sounds good, when can we meet?
"""


@tagged("post_install", "-at_install")
class TestLeadPartnerOnReply(MailCase):
    """A campaign lead gets its customer when the customer answers the agent."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot = new_test_user(
            cls.env,
            "reply_partner_bot",
            name="Seedian Assistant",
            email="assistant@seedian.example",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.salesperson = new_test_user(
            cls.env,
            "reply_partner_owner",
            name="Lead Owner",
            email="owner@seedian.example",
            notification_type="inbox",
            groups="sales_team.group_sale_salesman",
        )
        cls.env["crm.stage"].create(
            {"name": "Contacted", "sequence": 2, "prospecting_contacted": True}
        )
        cls.campaign = cls.env["utm.campaign"].create({"title": "Outreach"})
        cls.lead = cls._lead(cls.campaign)

    @classmethod
    def _lead(cls, campaign=None, **values):
        return cls.env["crm.lead"].create(
            {
                "name": "Acme",
                "type": "lead",
                "partner_name": "Acme",
                "contact_name": "Agustín Pérez",
                "function": "CTO",
                "phone": "+54 11 5555 0000",
                "email_from": CUSTOMER_EMAIL,
                "user_id": cls.salesperson.id,
                "campaign_id": campaign.id if campaign else False,
                **values,
            }
        )

    def _first_email(self, lead):
        """The agent's first email to `lead`, as `prospecting_send_email` sends it."""
        with self.mock_mail_gateway():
            result = (
                self.env["crm.lead"]
                .with_user(self.bot)
                .prospecting_send_email(lead.id, "Hello", "Hi there")
            )
        return self.env["mail.message"].browse(result["message_id"])

    def _reply(self, lead, email_from=f"Agustín Pérez <{CUSTOMER_EMAIL}>", extra=""):
        """The gateway receives an answer to the first email to `lead`."""
        first = self._first_email(lead)
        with self.mock_mail_gateway():
            self.format_and_process(
                REPLY_TEMPLATE,
                email_from,
                "replies@seedian.example",
                subject="Re: Hello",
                extra=f"In-Reply-To: {first.message_id}\n{extra}",
                target_model="crm.lead",
            )
        return lead.message_ids.filtered(lambda m: m.message_type == "email")

    def _partners(self, *names):
        return self.env["res.partner"].search([("name", "in", names)])

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_creates_company_and_contact(self):
        reply = self._reply(self.lead)

        contact = self.lead.partner_id
        self.assertEqual(contact.name, "Agustín Pérez")
        self.assertFalse(contact.is_company)
        self.assertEqual(contact.email_normalized, CUSTOMER_EMAIL)
        self.assertEqual(contact.function, "CTO")
        self.assertEqual(contact.phone, "+54 11 5555 0000")
        self.assertEqual(contact.parent_id.name, "Acme")
        self.assertTrue(contact.parent_id.is_company)
        self.assertEqual(reply.author_id, contact)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_new_company_has_no_person_email_phone_or_job(self):
        self._reply(self.lead)

        company = self.lead.partner_id.parent_id
        self.assertFalse(company.email)
        self.assertFalse(company.phone)
        self.assertFalse(company.function)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_new_company_gets_campaign_industry(self):
        industry = self.env["res.partner.industry"].create({"name": "Software"})
        self.campaign.prospecting_industry_id = industry

        self._reply(self.lead)

        self.assertEqual(self.lead.partner_id.parent_id.industry_id, industry)
        self.assertEqual(self.lead.partner_id.industry_id, industry)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_company_lead_reply_creates_contact_under_new_company(self):
        lead = self._lead(
            self.campaign, contact_name=False, email_from="info@acme.example"
        )

        reply = self._reply(lead, email_from="info@acme.example")

        contact = lead.partner_id
        self.assertEqual(contact.name, "info@acme.example")
        self.assertFalse(contact.is_company)
        self.assertEqual(contact.email_normalized, "info@acme.example")
        self.assertEqual(contact.parent_id.name, "Acme")
        self.assertTrue(contact.parent_id.is_company)
        self.assertFalse(contact.parent_id.email)
        self.assertEqual(lead.email_normalized, "info@acme.example")
        self.assertEqual(reply.author_id, contact)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_reuses_company_with_same_name(self):
        company = self.env["res.partner"].create(
            {"name": "  ACME ", "is_company": True}
        )

        self._reply(self.lead)

        self.assertEqual(self.lead.partner_id.name, "Agustín Pérez")
        self.assertEqual(self.lead.partner_id.parent_id, company)
        self.assertEqual(
            self.env["res.partner"].search_count(
                [("is_company", "=", True), ("name", "ilike", "acme")]
            ),
            1,
        )

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_company_lead_reply_creates_contact_under_existing_company(self):
        company = self.env["res.partner"].create(
            {"name": "Acme", "is_company": True, "email": "sales@acme.example"}
        )
        lead = self._lead(
            self.campaign, contact_name=False, email_from="info@acme.example"
        )

        reply = self._reply(lead, email_from="info@acme.example")

        contact = lead.partner_id
        self.assertEqual(contact.name, "info@acme.example")
        self.assertFalse(contact.is_company)
        self.assertEqual(contact.parent_id, company)
        self.assertEqual(contact.email_normalized, "info@acme.example")
        self.assertEqual(lead.email_normalized, "info@acme.example")
        self.assertEqual(company.email, "sales@acme.example")
        self.assertEqual(reply.author_id, contact)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_ignores_person_with_company_name(self):
        person = self.env["res.partner"].create({"name": "Acme"})

        self._reply(self.lead)

        company = self.lead.partner_id.parent_id
        self.assertTrue(company.is_company)
        self.assertNotEqual(company, person)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_reuses_partner_with_lead_email(self):
        existing = self.env["res.partner"].create(
            {"name": "Agustin P.", "email": CUSTOMER_EMAIL}
        )

        reply = self._reply(self.lead)

        self.assertEqual(self.lead.partner_id, existing)
        self.assertEqual(reply.author_id, existing)
        self.assertFalse(self._partners("Agustín Pérez", "Acme"))

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_from_other_address_creates_no_partner(self):
        reply = self._reply(self.lead, email_from="Mara <mara@acme.example>")

        self.assertFalse(self.lead.partner_id)
        self.assertFalse(reply.author_id)
        self.assertFalse(self._partners("Agustín Pérez", "Acme"))

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_auto_reply_creates_no_partner(self):
        reply = self._reply(self.lead, extra="Auto-Submitted: auto-replied\n")

        self.assertTrue(reply, "The automatic reply still lands on the lead.")
        self.assertFalse(self.lead.partner_id)
        self.assertFalse(self._partners("Agustín Pérez", "Acme"))

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_auto_generated_with_parameters_creates_no_partner(self):
        self._reply(self.lead, extra="Auto-Submitted: Auto-Generated; owner=x\n")

        self.assertFalse(self.lead.partner_id)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_auto_submitted_no_is_a_person(self):
        self._reply(self.lead, extra="Auto-Submitted: no\n")

        self.assertEqual(self.lead.partner_id.name, "Agustín Pérez")

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_on_lead_without_campaign_creates_no_partner(self):
        lead = self._lead()

        self._reply(lead)

        self.assertFalse(lead.partner_id)
        self.assertFalse(self._partners("Agustín Pérez", "Acme"))

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_reply_keeps_lead_partner(self):
        customer = self.env["res.partner"].create(
            {"name": "Rosa Díaz", "email": "rosa.diaz@initech.example"}
        )
        lead = self._lead(self.campaign, partner_id=customer.id)

        self._reply(lead, email_from="Rosa Díaz <rosa.diaz@initech.example>")

        self.assertEqual(lead.partner_id, customer)
        self.assertFalse(self._partners("Agustín Pérez", "Acme"))
