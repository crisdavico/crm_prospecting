# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import api, models
from odoo.tools.mail import email_normalize, parse_contact_from_email

# Context key of the mail gateway: the email it routes is an automatic reply.
AUTO_SUBMITTED = "prospecting_auto_submitted"

# Lead values that belong to the person, never to the company created for them.
PERSON_ONLY_FIELDS = ("email", "phone", "function")


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    @api.model
    def _message_route_process(self, message, message_dict, routes):
        """Tell `message_update` whether `message` is an automatic reply.

        An `Auto-Submitted` header other than "no" marks it (RFC 3834), as
        out-of-office and other automatic answers write it. Headers stop here:
        `message_update` only gets the parsed values.
        """
        header = (message.get("Auto-Submitted") or "").split(";")[0]
        keyword = header.strip().lower()
        automatic = bool(keyword) and keyword != "no"
        return super(
            MailThread, self.with_context(**{AUTO_SUBMITTED: automatic})
        )._message_route_process(message, message_dict, routes)


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def message_update(self, msg_dict, update_vals=None):
        """A campaign lead's customer answering becomes the lead's partner.

        When the answer comes from the lead's own email, is not an automatic
        reply, and the lead has no partner yet, the lead gets one: the partner
        that already has that email, otherwise a contact Odoo creates from the
        lead, under the company named as the lead's company. The answer is then
        authored by that partner.
        """
        if len(self) == 1 and self._prospecting_customer_answered(msg_dict):
            self._prospecting_assign_customer(msg_dict.get("author_id"))
            msg_dict["author_id"] = self.partner_id.id
        return super().message_update(msg_dict, update_vals=update_vals)

    def _prospecting_customer_answered(self, msg_dict):
        """Whether `msg_dict` is this campaign lead's customer answering in person."""
        self.ensure_one()
        return bool(
            self.campaign_id
            and not self.partner_id
            and self.email_normalized
            and email_normalize(msg_dict.get("email_from") or "")
            == self.email_normalized
            and not self.env.context.get(AUTO_SUBMITTED)
        )

    def _prospecting_assign_customer(self, author_id):
        """Give this lead the partner `author_id` when it has the lead's email.

        Otherwise Odoo creates the contact, under `_prospecting_company` when
        there is one, or under `_prospecting_new_company`. A lead without a
        person gets a contact named after its email under that company, never
        the company itself, so the lead keeps its own email.
        """
        self.ensure_one()
        author = self.env["res.partner"].browse(author_id).exists()
        if author and author.email_normalized == self.email_normalized:
            self._handle_partner_assignment(force_partner_id=author.id)
            return
        company = self._prospecting_company() or self._prospecting_new_company()
        if company and not self._prospecting_person_name():
            self.partner_id = self.env["res.partner"].create(
                self._prepare_customer_values(
                    self.email_normalized, is_company=False, parent_id=company.id
                )
            )
            return
        self._handle_partner_assignment(create_missing=True, with_parent=company)

    def _prospecting_new_company(self):
        """A new company named as this lead's company, or none without a name.

        It gets the lead's values as Odoo gives a new customer, except the
        person's own email, phone and job position, which stay on the contact,
        and the industry of the lead's campaign, which its contacts share.
        """
        self.ensure_one()
        name = (self.partner_name or "").strip()
        if not name:
            return self.env["res.partner"]
        values = self._prepare_customer_values(name, is_company=True)
        for field in PERSON_ONLY_FIELDS:
            values.pop(field, None)
        values["industry_id"] = self.campaign_id.prospecting_industry_id.id
        return self.env["res.partner"].create(values)

    def _prospecting_person_name(self):
        """The person's name Odoo's `_create_customer` would give the contact."""
        self.ensure_one()
        return self.contact_name or parse_contact_from_email(self.email_from)[0]

    def _prospecting_company(self):
        """The oldest company named as this lead's company, or none.

        Names match ignoring case and surrounding spaces. Only companies shared
        by every company, or of this lead's company, are considered.
        """
        self.ensure_one()
        name = (self.partner_name or "").strip()
        if not name:
            return self.env["res.partner"]
        companies = self.env["res.partner"].search(
            [
                ("is_company", "=", True),
                ("name", "ilike", name),
                ("company_id", "in", [False, self.company_id.id]),
            ],
            order="id",
        )
        return companies.filtered(
            lambda company: company.name.strip().casefold() == name.casefold()
        )[:1]
