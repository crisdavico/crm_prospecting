# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.tests import new_test_user, tagged

from odoo.addons.mail.tests.common import MailCase

CUSTOMER_EMAIL = "rosa.diaz@initech.example"


@tagged("post_install", "-at_install")
class TestLeadReplyThread(MailCase):
    """A reply from a campaign lead's chatter stays in the customer's email thread."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson = new_test_user(
            cls.env,
            "reply_thread_owner",
            name="Lead Owner",
            email="owner@seedian.example",
            notification_type="inbox",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.server = cls.env["ir.mail_server"].create(
            {"name": "Cold", "smtp_host": "smtp.cold.example"}
        )
        cls.campaign = cls.env["utm.campaign"].create(
            {"title": "Outreach", "prospecting_mail_server_id": cls.server.id}
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Rosa Díaz", "email": CUSTOMER_EMAIL}
        )
        cls.lead = cls._lead("Initech", cls.campaign)

    @classmethod
    def _lead(cls, name, campaign=None):
        return cls.env["crm.lead"].create(
            {
                "name": name,
                "type": "opportunity",
                "partner_id": cls.customer.id,
                "user_id": cls.salesperson.id,
                "campaign_id": campaign.id if campaign else False,
            }
        )

    def _customer_replied(self, lead, subject):
        """The customer's email answering the first outreach email lands on `lead`."""
        return lead.message_post(
            body="Sounds good, when can we meet?",
            subject=subject,
            message_type="email",
            subtype_xmlid="mail.mt_comment",
            author_id=self.customer.id,
        )

    def _post(self, lead, **kwargs):
        """The salesperson clicks "Send message": no subject, no server."""
        with self.mock_mail_gateway():
            message = lead.with_user(self.salesperson).message_post(
                body="Monday at 3pm?",
                message_type="comment",
                subtype_xmlid=kwargs.pop("subtype_xmlid", "mail.mt_comment"),
                partner_ids=self.customer.ids,
                **kwargs,
            )
        return message

    def _composer(self, lead, **vals):
        return (
            self.env["mail.compose.message"]
            .with_user(self.salesperson)
            .with_context(
                default_model="crm.lead",
                default_res_ids=lead.ids,
                default_composition_mode="comment",
            )
            .create(
                {"body": "Monday at 3pm?", "partner_ids": self.customer.ids, **vals}
            )
        )

    def _sent_to_customer(self):
        return [
            mail
            for mail in self._mails
            if any(CUSTOMER_EMAIL in recipient for recipient in mail["email_to"])
        ]

    def _servers_used(self):
        return [
            call.kwargs["mail_server_id"]
            for call in self.send_email_mocked.call_args_list
        ]

    def test_chatter_reply_keeps_the_subject_of_the_last_email(self):
        self._customer_replied(self.lead, "Re: Odoo and AI at Initech")

        self._post(self.lead)

        sent = self._sent_to_customer()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["subject"], "Re: Odoo and AI at Initech")

    def test_chatter_reply_adds_re_to_a_first_email_subject(self):
        self.lead.message_post(
            body="Hi Rosa",
            subject="Odoo and AI at Initech",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

        self._post(self.lead)

        sent = self._sent_to_customer()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["subject"], "Re: Odoo and AI at Initech")

    def test_internal_notes_do_not_set_the_reply_subject(self):
        self._customer_replied(self.lead, "Re: Odoo and AI at Initech")
        self.lead.message_post(
            body="Call her first",
            subject="Internal",
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

        self._post(self.lead)

        self.assertEqual(
            self._sent_to_customer()[0]["subject"], "Re: Odoo and AI at Initech"
        )

    def test_composer_suggests_the_subject_of_the_last_email(self):
        self._customer_replied(self.lead, "Re: Odoo and AI at Initech")

        composer = self._composer(self.lead)

        self.assertEqual(composer.subject, "Re: Odoo and AI at Initech")

    def test_chatter_reply_on_a_lead_without_emails_keeps_the_lead_name(self):
        self._post(self.lead)

        self.assertEqual(self._sent_to_customer()[0]["subject"], "Initech")

    def test_chatter_reply_without_a_campaign_keeps_the_lead_name(self):
        lead = self._lead("Globex")
        self._customer_replied(lead, "Re: Odoo and AI at Globex")

        self._post(lead)

        self.assertEqual(self._sent_to_customer()[0]["subject"], "Globex")

    def test_chatter_reply_goes_through_the_campaign_mail_server(self):
        message = self._post(self.lead)

        self.assertEqual(message.mail_server_id, self.server)
        self.assertEqual(len(self._sent_to_customer()), 1)
        self.assertEqual(set(self._servers_used()), {self.server.id})

    def test_composer_reply_goes_through_the_campaign_mail_server(self):
        composer = self._composer(self.lead, subject="Our call")
        with self.mock_mail_gateway():
            composer._action_send_mail()

        self.assertEqual(len(self._sent_to_customer()), 1)
        self.assertEqual(set(self._servers_used()), {self.server.id})

    def test_an_explicit_mail_server_is_kept(self):
        other = self.env["ir.mail_server"].create(
            {"name": "Other", "smtp_host": "smtp.other.example"}
        )

        message = self._post(self.lead, mail_server_id=other.id)

        self.assertEqual(message.mail_server_id, other)

    def test_internal_note_keeps_odoo_choosing_the_server(self):
        message = self._post(self.lead, subtype_xmlid="mail.mt_note")

        self.assertFalse(message.mail_server_id)

    def test_lead_without_a_campaign_server_keeps_odoo_choosing_the_server(self):
        lead = self._lead("Globex", self.env["utm.campaign"].create({"title": "Plain"}))

        message = self._post(lead)

        self.assertFalse(message.mail_server_id)
        self.assertEqual(self._servers_used(), [False])
