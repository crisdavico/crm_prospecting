# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools.mail import email_normalize, formataddr

from odoo.addons.mail.tests.common import MailCase

REPLY_TO = "replies@outreach.example"


@tagged("post_install", "-at_install")
class TestLeadReplyTo(MailCase):
    """Every email on a lead of a campaign with a Reply-To answers to that address."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot = new_test_user(
            cls.env,
            "reply_to_assistant",
            name="Seedian Assistant",
            email="assistant@outreach.example",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.salesperson = new_test_user(
            cls.env,
            "reply_to_owner",
            name="Lead Owner",
            email="owner@seedian.example",
            notification_type="inbox",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.env["crm.stage"].create(
            {"name": "Contacted", "sequence": 2, "prospecting_contacted": True}
        )
        cls.team = cls.env["crm.team"].create({"name": "Outbound"})
        cls.campaign = cls.env["utm.campaign"].create(
            {"title": "Outreach", "prospecting_reply_to": REPLY_TO}
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Rosa Díaz", "email": "rosa.diaz@initech.example"}
        )
        cls.lead = cls._lead("Acme", "agustin.perez@acme.example", cls.campaign)

    @classmethod
    def _lead(cls, name, email, campaign=None):
        return cls.env["crm.lead"].create(
            {
                "name": name,
                "type": "lead",
                "contact_name": name,
                "email_from": email,
                "user_id": cls.salesperson.id,
                "team_id": cls.team.id,
                "campaign_id": campaign.id if campaign else False,
            }
        )

    def _post(self, lead):
        """The salesperson writes to the customer from the lead's chatter."""
        with self.mock_mail_gateway():
            message = lead.with_user(self.salesperson).message_post(
                body="Following up",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                partner_ids=self.customer.ids,
            )
        return message

    def _reply_to_sent_to(self, email):
        return [
            mail["reply_to"]
            for mail in self._mails
            if any(email in recipient for recipient in mail["email_to"])
        ]

    def test_agent_email_replies_to_the_campaign_address(self):
        with self.mock_mail_gateway():
            result = (
                self.env["crm.lead"]
                .with_user(self.bot)
                .prospecting_send_email(self.lead.id, "Hello", "Hi there")
            )

        message = self.env["mail.message"].browse(result["message_id"])
        self.assertEqual(email_normalize(message.reply_to), REPLY_TO)
        reply_tos = self._reply_to_sent_to("agustin.perez@acme.example")
        self.assertEqual(len(reply_tos), 1)
        self.assertEqual(email_normalize(reply_tos[0]), REPLY_TO)

    def test_chatter_message_replies_to_the_campaign_address(self):
        message = self._post(self.lead)

        self.assertEqual(email_normalize(message.reply_to), REPLY_TO)
        reply_tos = self._reply_to_sent_to("rosa.diaz@initech.example")
        self.assertEqual(len(reply_tos), 1)
        self.assertEqual(email_normalize(reply_tos[0]), REPLY_TO)
        self.assertIn("Lead Owner", reply_tos[0])

    def test_composer_message_replies_to_the_campaign_address(self):
        composer = (
            self.env["mail.compose.message"]
            .with_user(self.salesperson)
            .with_context(
                default_model="crm.lead",
                default_res_ids=self.lead.ids,
                default_composition_mode="comment",
            )
            .create(
                {
                    "body": "Following up",
                    "subject": "Our call",
                    "partner_ids": self.customer.ids,
                }
            )
        )
        with self.mock_mail_gateway():
            composer._action_send_mail()

        reply_tos = self._reply_to_sent_to("rosa.diaz@initech.example")
        self.assertEqual(len(reply_tos), 1)
        self.assertEqual(email_normalize(reply_tos[0]), REPLY_TO)

    def test_batch_composer_replies_to_each_lead_campaign_address(self):
        other = self._lead("Globex", "info@globex.example")
        composer = (
            self.env["mail.compose.message"]
            .with_context(
                default_model="crm.lead",
                default_res_ids=(self.lead | other).ids,
                default_composition_mode="comment",
            )
            .create({"body": "Following up", "subject": "Our call"})
        )

        values = composer._prepare_mail_values((self.lead | other).ids)

        self.assertEqual(email_normalize(values[self.lead.id]["reply_to"]), REPLY_TO)
        self.assertNotEqual(email_normalize(values[other.id]["reply_to"]), REPLY_TO)

    def test_lead_of_a_campaign_without_reply_to_keeps_odoo_reply_to(self):
        plain = self.env["utm.campaign"].create({"title": "Plain"})
        lead = self._lead("Initech", "info@initech.example", plain)
        lead_without_campaign = self._lead("Globex", "info@globex.example")

        message = self._post(lead)
        reference = self._post(lead_without_campaign)

        self.assertNotEqual(email_normalize(message.reply_to), REPLY_TO)
        self.assertEqual(message.reply_to, reference.reply_to)

    def test_reply_to_is_stored_as_the_clean_address(self):
        campaign = self.env["utm.campaign"].create(
            {"title": "Named", "prospecting_reply_to": f"  Replies <{REPLY_TO}> "}
        )
        self.assertEqual(campaign.prospecting_reply_to, REPLY_TO)
        campaign.prospecting_reply_to = REPLY_TO.upper()
        self.assertEqual(campaign.prospecting_reply_to, REPLY_TO)

    def test_salesperson_can_duplicate_a_campaign(self):
        copy = self.campaign.with_user(self.salesperson).copy()
        self.assertTrue(copy.exists())
        self.assertFalse(copy.sudo().prospecting_reply_to)

    def test_admin_duplicate_keeps_the_reply_to(self):
        self.assertEqual(self.campaign.copy().prospecting_reply_to, REPLY_TO)

    def test_reply_to_must_be_one_email_address(self):
        for value in ("not an email", f"{REPLY_TO}, other@outreach.example"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.campaign.prospecting_reply_to = value
                self.campaign.flush_recordset()

    def test_named_reply_to_sends_only_its_address(self):
        self.campaign.prospecting_reply_to = f"Replies <{REPLY_TO}>"

        message = self._post(self.lead)

        self.assertEqual(message.reply_to, formataddr(("Lead Owner", REPLY_TO)))
        reply_tos = self._reply_to_sent_to("rosa.diaz@initech.example")
        self.assertEqual(reply_tos, [formataddr(("Lead Owner", REPLY_TO))])

    def test_only_admins_can_change_the_reply_to(self):
        Campaign = self.env["utm.campaign"].with_user(self.salesperson)
        with self.assertRaises(AccessError):
            Campaign.browse(self.campaign.id).write(
                {"prospecting_reply_to": "attacker@evil.example"}
            )
        with self.assertRaises(AccessError):
            Campaign.create(
                {"title": "Sneaky", "prospecting_reply_to": "attacker@evil.example"}
            )
        self.assertEqual(self.campaign.prospecting_reply_to, REPLY_TO)

    def test_admin_form_shows_the_reply_to_only_to_admins(self):
        Campaign = self.env["utm.campaign"]
        arch = Campaign.get_view(view_type="form")["arch"]
        self.assertIn('name="prospecting_reply_to"', arch)
        salesman = new_test_user(
            self.env,
            login="reply_to_salesman",
            groups="sales_team.group_sale_salesman",
        )
        arch = Campaign.with_user(salesman).get_view(view_type="form")["arch"]
        self.assertNotIn('name="prospecting_reply_to"', arch)
