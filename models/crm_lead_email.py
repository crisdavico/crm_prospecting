# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL, formataddr, html2plaintext
from odoo.tools.misc import clean_context

# How long an email to a lead blocks sending the same subject and body again.
EMAIL_REPEAT_WINDOW = timedelta(hours=24)

# `mail.notification` statuses of an email that did not reach the SMTP server.
FAILED_EMAIL_STATUSES = frozenset({"bounce", "exception", "canceled"})

# Notification parameter of `prospecting_send_email`: notify no customer follower.
CUSTOMER_ONLY = "prospecting_customer_only"


class CrmLead(models.Model):
    """Emails the prospecting agent sends to a lead's customer."""

    _inherit = "crm.lead"

    @api.model
    def prospecting_send_email(self, lead_id, subject, body):
        """Send `subject` and the plain text `body` to the customer of lead `lead_id`.

        The email goes to the lead's partner when it has an email, otherwise to the
        lead's own email without creating a partner. It is posted on the lead's
        chatter, authored by the caller with their signature, and sent right after
        the transaction commits. Internal followers get their usual notification;
        customer followers get nothing. Recipients and sending are set here, never
        taken from the caller's context.

        The same subject and body sent to the same address of the lead in the last
        24 hours is not sent again, unless that email failed.

        Returns ``{"status": "queued" | "duplicate", "message_id": id, "email": str}``,
        where a duplicate answers the earlier message.
        """
        subject = (subject or "").strip()
        if not subject:
            raise UserError(self.env._("The email subject is required."))
        lead = self.browse(lead_id)
        if not lead.exists():
            raise UserError(self.env._("Lead %(id)s does not exist.", id=lead_id))
        lead.check_access("read")
        if not lead.active:
            raise UserError(
                self.env._(
                    "Lead %(id)s is lost or archived: no email is sent to it.",
                    id=lead.id,
                )
            )
        recipient, email = lead._prospecting_email_recipient()
        html = Markup("<br>").join((body or "").splitlines())

        lead._prospecting_email_lock()
        duplicate = lead._prospecting_email_duplicate(email, subject, html)
        if duplicate:
            return {"status": "duplicate", "message_id": duplicate.id, "email": email}

        context = {
            **clean_context(self.env.context),
            "mail_notify_force_send": True,
            "mail_notify_author": False,
            "mail_notify_author_mention": False,
            "mail_post_autofollow": False,
            "mail_post_autofollow_author_skip": False,
        }
        # A whole new context drops the caller's `default_*` keys.
        message = lead.with_env(self.env(context=context)).message_post(
            body=html,
            subject=subject,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            author_id=self.env.user.partner_id.id,
            force_send=True,
            send_after_commit=True,
            **recipient,
            **{CUSTOMER_ONLY: True},
        )
        return {"status": "queued", "message_id": message.id, "email": email}

    @api.model
    def prospecting_email_status(self, message_id):
        """Whether the email `prospecting_send_email` posted as `message_id` was sent.

        Answers only for emails to the customer of a lead the caller can read.

        Returns ``{"status": "sent" | "failed" | "pending", "message_id": id,
        "email": str}``, plus ``"failure_reason"`` when it failed. "sent" means the
        SMTP server accepted the email.
        """
        message = self.env["mail.message"].sudo().browse(message_id).exists()
        if message.model == self._name:
            # Before telling anything about the message, even what kind it is.
            self.browse(message.res_id).check_access("read")
        notification = (
            message._prospecting_customer_notifications()[:1]
            if message.model == self._name
            else self.env["mail.notification"]
        )
        if not notification:
            raise UserError(
                self.env._(
                    "Message %(id)s is not an email to a lead's customer.",
                    id=message_id,
                )
            )
        result = {
            "message_id": message.id,
            "email": notification._prospecting_email(),
        }
        if notification.notification_status == "sent":
            return {**result, "status": "sent"}
        if notification.notification_status in FAILED_EMAIL_STATUSES:
            return {
                **result,
                "status": "failed",
                "failure_reason": notification.format_failure_reason(),
            }
        return {**result, "status": "pending"}

    def _prospecting_email_recipient(self):
        """`message_post` recipient arguments and the address, for this lead."""
        self.ensure_one()
        if self.partner_id.email_normalized:
            return {
                "partner_ids": self.partner_id.ids
            }, self.partner_id.email_normalized
        if self.email_normalized:
            address = formataddr((self.contact_name or "", self.email_normalized))
            return {"outgoing_email_to": address}, self.email_normalized
        raise UserError(
            self.env._(
                "Lead %(id)s has no customer email: no email is sent.", id=self.id
            )
        )

    def _prospecting_email_lock(self):
        """Serialize sends to this lead, like `_prospecting_dedup_lock` for creates.

        Updating the lead's row makes a concurrent send wait, then fail with a
        serialization error Odoo retries, so the retry sees the first email.
        """
        self.ensure_one()
        self.env.cr.execute(
            SQL(
                "UPDATE crm_lead SET write_date = write_date WHERE id = %s",
                self.id,
            )
        )

    def _prospecting_email_duplicate(self, email, subject, html):
        """The latest unfailed email with the same content to `email` on this lead."""
        self.ensure_one()
        recent = (
            self.env["mail.message"]
            .sudo()
            .search(
                [
                    ("model", "=", self._name),
                    ("res_id", "=", self.id),
                    ("message_type", "=", "comment"),
                    ("subject", "=", subject),
                    (
                        "create_date",
                        ">=",
                        fields.Datetime.now() - EMAIL_REPEAT_WINDOW,
                    ),
                ],
                order="id desc",
            )
        )
        text = html2plaintext(html)
        for message in recent:
            if html2plaintext(message.body) != text:
                continue
            notifications = message._prospecting_customer_notifications()
            if any(
                notification._prospecting_email() == email
                and notification.notification_status not in FAILED_EMAIL_STATUSES
                for notification in notifications
            ):
                return message
        return self.env["mail.message"]

    def _get_notify_valid_parameters(self):
        return super()._get_notify_valid_parameters() | {CUSTOMER_ONLY}

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        """Without customer followers when `prospecting_send_email` posts."""
        customer_only = kwargs.pop(CUSTOMER_ONLY, False)
        recipients = super()._notify_get_recipients(
            message, msg_vals=msg_vals, **kwargs
        )
        if not customer_only:
            return recipients
        msg_vals = msg_vals or {}
        direct = set(
            msg_vals["partner_ids"]
            if "partner_ids" in msg_vals
            else message.sudo().partner_ids.ids
        )
        return [
            recipient
            for recipient in recipients
            if not recipient["id"]
            or not recipient["share"]
            or recipient["id"] in direct
        ]


class MailMessage(models.Model):
    _inherit = "mail.message"

    def _prospecting_customer_notifications(self):
        """The email notifications of this message to its own recipients.

        Those are the customer `prospecting_send_email` wrote to, never a follower.
        """
        self.ensure_one()
        message = self.sudo()
        return message.notification_ids.filtered(
            lambda notification: notification.notification_type == "email"
            and (
                notification.mail_email_address
                or notification.res_partner_id in message.partner_ids
            )
        )


class MailNotification(models.Model):
    _inherit = "mail.notification"

    def _prospecting_email(self):
        """The address this email notification went to."""
        self.ensure_one()
        return self.mail_email_address or self.res_partner_id.email_normalized
