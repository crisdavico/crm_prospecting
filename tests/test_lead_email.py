# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from contextlib import contextmanager
from datetime import timedelta

from psycopg2.errors import SerializationFailure

from odoo import SUPERUSER_ID, api, fields, sql_db
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.tests import BaseCase, new_test_user, tagged
from odoo.tests.common import get_db_name
from odoo.tools import mute_logger

from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.addons.mail.tests.common import MailCase


@tagged("post_install", "-at_install")
class TestLeadEmail(MailCase):
    """`prospecting_send_email`: one email to the lead's customer, sent from Odoo."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot = new_test_user(
            cls.env,
            "seedian_assistant",
            name="Seedian Assistant",
            email="assistant@seedian.example",
            signature="Seedian Assistant, your sales helper",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.salesperson = new_test_user(
            cls.env,
            "lead_owner",
            name="Lead Owner",
            email="owner@seedian.example",
            notification_type="inbox",
            groups="sales_team.group_sale_salesman",
        )
        cls.Lead = cls.env["crm.lead"].with_user(cls.bot)
        cls.lead = cls.env["crm.lead"].create(
            {
                "name": "Acme",
                "type": "lead",
                "contact_name": "Agustín Pérez",
                "email_from": "agustin.perez@acme.example",
                "user_id": cls.salesperson.id,
            }
        )
        cls.customer = cls.env["res.partner"].create(
            {"name": "Rosa Díaz", "email": "rosa.diaz@initech.example"}
        )
        cls.partner_lead = cls.env["crm.lead"].create(
            {
                "name": "Initech",
                "type": "opportunity",
                "partner_id": cls.customer.id,
                "user_id": cls.salesperson.id,
            }
        )

    def _send(self, lead=None, subject="Hello", body="Hi there", **context):
        Lead = self.Lead.with_context(**context) if context else self.Lead
        with self.mock_mail_gateway():
            result = Lead.prospecting_send_email((lead or self.lead).id, subject, body)
        return result

    @contextmanager
    def _smtp_refuses(self, email):
        """Within `mock_mail_gateway`, the SMTP server refuses mail to `email`."""
        send = self.send_email_mocked.side_effect

        def _send_email(model, message, **kwargs):
            if email in message["To"]:
                raise MailDeliveryException("Mailbox unavailable")
            return send(model, message, **kwargs)

        self.send_email_mocked.side_effect = _send_email
        try:
            yield
        finally:
            self.send_email_mocked.side_effect = send

    def _sent_to(self, email):
        return [
            mail
            for mail in self._mails
            if any(email in recipient for recipient in mail["email_to"])
        ]

    def _customer_messages(self, lead):
        return self.env["mail.message"].search(
            [
                ("model", "=", "crm.lead"),
                ("res_id", "=", lead.id),
                ("message_type", "=", "comment"),
            ]
        )

    # Sending (S2, S3, S11)

    def test_email_goes_to_lead_email_without_creating_a_partner(self):
        partners_before = self.env["res.partner"].search_count([])
        result = self._send(subject="Your quote", body="Hi Agustín")

        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["email"], "agustin.perez@acme.example")
        sent = self._sent_to("agustin.perez@acme.example")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["subject"], "Your quote")
        message = self.env["mail.message"].browse(result["message_id"])
        self.assertEqual(message.model, "crm.lead")
        self.assertEqual(message.res_id, self.lead.id)
        self.assertEqual(message.message_type, "comment")
        self.assertEqual(message.subtype_id, self.env.ref("mail.mt_comment"))
        self.assertEqual(self.env["res.partner"].search_count([]), partners_before)
        self.assertFalse(self.lead.partner_id)
        self.assertEqual(self.lead.email_from, "agustin.perez@acme.example")

    def test_email_goes_to_the_linked_partner(self):
        result = self._send(lead=self.partner_lead)

        self.assertEqual(result["email"], "rosa.diaz@initech.example")
        self.assertEqual(len(self._sent_to("rosa.diaz@initech.example")), 1)
        message = self.env["mail.message"].browse(result["message_id"])
        self.assertEqual(message.partner_ids, self.customer)

    def test_status_is_sent_once_the_smtp_server_accepts_it(self):
        result = self._send()
        status = self.Lead.prospecting_email_status(result["message_id"])
        self.assertEqual(
            status,
            {
                "status": "sent",
                "message_id": result["message_id"],
                "email": "agustin.perez@acme.example",
            },
        )

    def test_status_is_failed_with_reason_when_smtp_refuses_it(self):
        with self.mock_mail_gateway(), self._smtp_refuses("agustin.perez@acme.example"):
            result = self.Lead.prospecting_send_email(self.lead.id, "Hello", "Hi")
        status = self.Lead.prospecting_email_status(result["message_id"])
        self.assertEqual(status["status"], "failed")
        self.assertTrue(status["failure_reason"])

    def test_caller_context_cannot_change_recipients_or_sending(self):
        result = self._send(
            lead=self.partner_lead,
            mail_notify_force_send=False,
            mail_post_autofollow=True,
            mail_notify_author=True,
            default_partner_ids=[self.env.ref("base.partner_admin").id],
        )
        status = self.Lead.prospecting_email_status(result["message_id"])
        self.assertEqual(status["status"], "sent")
        message = self.env["mail.message"].browse(result["message_id"])
        self.assertEqual(message.partner_ids, self.customer)
        self.assertNotIn(self.customer, self.partner_lead.message_partner_ids)
        self.assertFalse(self._sent_to("assistant@seedian.example"))

    # Missing address (S4)

    def test_lead_without_email_sends_nothing(self):
        self.lead.email_from = False
        with self.assertRaises(UserError):
            self._send()
        self.assertFalse(self._mails)
        self.assertFalse(self._customer_messages(self.lead))

    def test_linked_partner_without_email_falls_back_to_lead_email(self):
        self.lead.partner_id = self.env["res.partner"].create({"name": "No mail"})
        self.lead.email_from = "agustin.perez@acme.example"
        self.lead.partner_id.email = False
        result = self._send()
        self.assertEqual(result["email"], "agustin.perez@acme.example")

    # Body and subject (S5, S6)

    def test_body_is_escaped_and_newlines_become_line_breaks(self):
        self._send(body="<b>Hola</b>\nSegunda línea")
        body = self._sent_to("agustin.perez@acme.example")[0]["body"]
        self.assertIn("&lt;b&gt;Hola&lt;/b&gt;<br>Segunda línea", body)
        self.assertNotIn("<b>Hola</b>", body)

    def test_blank_subject_is_rejected_before_sending(self):
        for subject in ("", "   ", None):
            with self.subTest(subject=subject), self.assertRaises(UserError):
                self._send(subject=subject)
        self.assertFalse(self._customer_messages(self.lead))

    # Sender and signature (S8)

    def test_email_is_authored_by_the_caller_with_their_signature(self):
        result = self._send()
        message = self.env["mail.message"].browse(result["message_id"])
        self.assertEqual(message.author_id, self.bot.partner_id)
        sent = self._sent_to("agustin.perez@acme.example")[0]
        self.assertIn("assistant@seedian.example", sent["email_from"])
        self.assertIn("Seedian Assistant, your sales helper", sent["body"])

    # Followers (S9)

    def test_internal_followers_are_notified_and_customer_followers_are_not(self):
        follower = self.env["res.partner"].create(
            {"name": "Customer follower", "email": "follower@acme.example"}
        )
        self.lead.message_subscribe(partner_ids=follower.ids)
        result = self._send()

        notified = (
            self.env["mail.notification"]
            .search([("mail_message_id", "=", result["message_id"])])
            .res_partner_id
        )
        self.assertIn(self.salesperson.partner_id, notified)
        self.assertNotIn(follower, notified)
        self.assertFalse(self._sent_to("follower@acme.example"))

    # Lead state and reach (S10)

    def test_lost_or_archived_lead_is_refused(self):
        self.lead.action_set_lost()
        with self.assertRaises(UserError):
            self._send()
        self.assertFalse(self._mails)

    def test_lead_the_caller_cannot_read_is_refused(self):
        other = new_test_user(
            self.env, "other_seller", groups="sales_team.group_sale_salesman"
        )
        with self.assertRaises(AccessError), self.mock_mail_gateway():
            self.env["crm.lead"].with_user(other).prospecting_send_email(
                self.lead.id, "Hello", "Hi"
            )
        self.assertFalse(self._mails)

    def test_missing_lead_is_refused(self):
        with self.assertRaises(MissingError):
            self._send(lead=self.env["crm.lead"].browse(999999999))

    # Repeat guard (S13)

    def test_same_subject_and_body_within_a_day_is_a_duplicate(self):
        first = self._send(subject="Hello", body="Hi\nthere")
        second = self._send(subject="Hello", body="Hi\nthere")
        self.assertEqual(
            second,
            {
                "status": "duplicate",
                "message_id": first["message_id"],
                "email": "agustin.perez@acme.example",
            },
        )
        self.assertFalse(self._mails)
        self.assertEqual(len(self._customer_messages(self.lead)), 1)

    def test_different_content_or_after_a_day_goes_through(self):
        first = self._send(subject="Hello", body="Hi")
        self.assertEqual(
            self._send(subject="Hello", body="Hi again")["status"], "queued"
        )
        self.assertEqual(self._send(subject="Other", body="Hi")["status"], "queued")
        self.env.cr.execute(
            "UPDATE mail_message SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(hours=25), first["message_id"]),
        )
        self.env.invalidate_all()
        self.assertEqual(self._send(subject="Hello", body="Hi")["status"], "queued")

    def test_a_failed_email_can_be_sent_again(self):
        with self.mock_mail_gateway(), self._smtp_refuses("agustin.perez@acme.example"):
            self.Lead.prospecting_send_email(self.lead.id, "Hello", "Hi")
        self.assertEqual(self._send(subject="Hello", body="Hi")["status"], "queued")

    # Status method (S15)

    def test_status_of_a_lead_the_caller_cannot_read_is_refused(self):
        result = self._send()
        other = new_test_user(
            self.env, "status_seller", groups="sales_team.group_sale_salesman"
        )
        with self.assertRaises(AccessError):
            self.env["crm.lead"].with_user(other).prospecting_email_status(
                result["message_id"]
            )

    def test_status_of_a_message_that_is_not_a_lead_email_is_refused(self):
        note = self.lead.message_post(body="Internal note")
        for message_id in (note.id, 999999999):
            with self.subTest(message_id=message_id), self.assertRaises(MissingError):
                self.Lead.prospecting_email_status(message_id)


@tagged("post_install", "-at_install")
class TestLeadEmailConcurrency(BaseCase):
    """Two sends of the same email at once: the later one never sends it again."""

    def test_a_send_whose_snapshot_misses_the_first_email_is_cancelled(self):
        db = sql_db.db_connect(get_db_name())
        lead_id = None
        try:
            with db.cursor() as setup_cr:
                lead_id = (
                    api.Environment(setup_cr, SUPERUSER_ID, {})["crm.lead"]
                    .create(
                        {
                            "name": "Concurrent email",
                            "email_from": "concurrent@example.com",
                        }
                    )
                    .id
                )
            with db.cursor() as late_cr:
                late = api.Environment(late_cr, SUPERUSER_ID, {})["crm.lead"]
                # The late call's snapshot starts here, as an RPC request's would.
                late.search_count([])
                with db.cursor() as first_cr:
                    first = api.Environment(first_cr, SUPERUSER_ID, {})["crm.lead"]
                    sent = first.prospecting_send_email(lead_id, "Hello", "Hi")
                    self.assertEqual(sent["status"], "queued")
                with (
                    mute_logger("odoo.sql_db"),
                    self.assertRaises(SerializationFailure),
                ):
                    late.prospecting_send_email(lead_id, "Hello", "Hi")
                late_cr.rollback()
            with db.cursor() as retry_cr:
                retry = api.Environment(retry_cr, SUPERUSER_ID, {})["crm.lead"]
                again = retry.prospecting_send_email(lead_id, "Hello", "Hi")
                self.assertEqual(again["status"], "duplicate")
                self.assertEqual(again["message_id"], sent["message_id"])
                retry_cr.rollback()
        finally:
            if lead_id:
                with db.cursor() as cleanup_cr:
                    api.Environment(cleanup_cr, SUPERUSER_ID, {})["crm.lead"].browse(
                        lead_id
                    ).unlink()
