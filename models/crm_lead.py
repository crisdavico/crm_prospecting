# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

import re
import unicodedata
from urllib.parse import urlsplit

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import SQL
from odoo.tools.mail import email_normalize

FIT_SCORE_MIN = 0
FIT_SCORE_MAX = 100

GENERIC_MAILBOXES = frozenset(
    {
        "admin",
        "administracion",
        "atencion",
        "comercial",
        "compras",
        "consultas",
        "contact",
        "contacto",
        "hello",
        "hola",
        "info",
        "informes",
        "mail",
        "office",
        "recepcion",
        "rrhh",
        "sales",
        "soporte",
        "support",
        "ventas",
    }
)
"""Mailbox names that reach a shared inbox, not a person. Kept in step with the
prospecting agent's own list (`_GENERIC_MAILBOXES` in its `agent/tools/leads.py`)."""

DEDUP_LOCK_TABLE = "crm_prospecting_dedup_lock"
"""One-row table every `prospecting_create_lead` call updates before searching.

Odoo runs each request at REPEATABLE READ, with a snapshot taken at its first query.
A lock taken later would let a waiting call search that older snapshot and miss the
lead another call just committed. Updating one shared row instead makes PostgreSQL
cancel the waiting call with a serialization failure once the other commits, and Odoo
retries the whole request with a fresh snapshot that sees the new lead."""


def text_key(value):
    """`value` without accents, case or repeated spaces; False when blank."""
    if not value:
        return False
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(plain.casefold().split()) or False


def cuit_key(value):
    """The digits of a CUIT, so `30-71234567-8` and `30712345678` match."""
    digits = re.sub(r"\D", "", value or "")
    return digits or False


SHARED_HOSTS = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "tiktok.com",
        "linktr.ee",
        "wa.me",
        "whatsapp.com",
        "google.com",
        "goo.gl",
        "mercadolibre.com.ar",
    }
)
"""Platforms that host pages of many companies: their host identifies no company."""


def _host_and_path(value):
    """The lowercase host without `www.` and the path; empty for unparsable text."""
    text = (value or "").strip()
    if not text:
        return "", ""
    if "://" not in text:
        text = f"//{text}"
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
    except ValueError:
        return "", ""
    host = host.removeprefix("www.")
    return host, parts.path


def website_key(value):
    """The host of a website without `www.`: `https://www.acme.com/x` is `acme.com`.

    False for a page on a platform shared by many companies (`SHARED_HOSTS`).
    """
    host, _path = _host_and_path(value)
    if any(host == shared or host.endswith(f".{shared}") for shared in SHARED_HOSTS):
        return False
    return host or False


def linkedin_key(value):
    """A LinkedIn profile URL without scheme, country subdomain, query or end slash."""
    host, path = _host_and_path(value)
    if not host:
        return False
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        host = "linkedin.com"
    path = path.rstrip("/").lower()
    return f"{host}{path}"


def personal_email_key(value):
    """The normalized email, or False when it is blank or reaches a shared inbox."""
    email = email_normalize(value or "")
    if not email or email.partition("@")[0] in GENERIC_MAILBOXES:
        return False
    return email


class CrmLead(models.Model):
    """What the prospecting agent produces for each lead it finds."""

    _inherit = "crm.lead"

    prospecting_fit_score = fields.Integer(
        help="How well the company fits the campaign profile, from 0 to 100.",
    )
    prospecting_cuit = fields.Char(
        string="Prospecting CUIT",
        index=True,
        help="Tax ID of the company, used to detect duplicate leads.",
    )
    prospecting_run_ref = fields.Char(
        string="Prospecting Run Reference",
        help="Agent thread or run that produced the lead.",
    )
    prospecting_linkedin = fields.Char(
        string="LinkedIn Profile",
        help="LinkedIn profile of the lead's contact, used to detect duplicate leads.",
    )
    prospecting_outreach_date = fields.Datetime(
        readonly=True,
        copy=False,
        index=True,
        help="When the email agent last emailed this lead.",
    )

    # Normalized keys `prospecting_create_lead` searches on.
    prospecting_cuit_key = fields.Char(
        compute="_compute_prospecting_keys", store=True, index=True
    )
    prospecting_website_key = fields.Char(
        compute="_compute_prospecting_keys", store=True, index=True
    )
    prospecting_company_key = fields.Char(
        compute="_compute_prospecting_keys", store=True, index=True
    )
    prospecting_contact_key = fields.Char(
        compute="_compute_prospecting_keys", store=True, index=True
    )
    prospecting_linkedin_key = fields.Char(
        compute="_compute_prospecting_keys", store=True, index=True
    )
    email_normalized = fields.Char(index=True)

    @api.depends(
        "prospecting_cuit",
        "website",
        "partner_name",
        "contact_name",
        "prospecting_linkedin",
    )
    def _compute_prospecting_keys(self):
        for lead in self:
            lead.prospecting_cuit_key = cuit_key(lead.prospecting_cuit)
            lead.prospecting_website_key = website_key(lead.website)
            lead.prospecting_company_key = text_key(lead.partner_name)
            lead.prospecting_contact_key = text_key(lead.contact_name)
            lead.prospecting_linkedin_key = linkedin_key(lead.prospecting_linkedin)

    def init(self):
        super().init()
        self.env.cr.execute(
            SQL(
                "CREATE TABLE IF NOT EXISTS %s (id integer PRIMARY KEY, calls bigint "
                "NOT NULL DEFAULT 0); INSERT INTO %s (id) VALUES (1) "
                "ON CONFLICT (id) DO NOTHING",
                SQL.identifier(DEDUP_LOCK_TABLE),
                SQL.identifier(DEDUP_LOCK_TABLE),
            )
        )

    @api.model
    def _prospecting_dedup_lock(self):
        """Serialize `prospecting_create_lead` calls (see `DEDUP_LOCK_TABLE`).

        Raises a serialization failure, which Odoo retries, when another call
        committed after this request's snapshot.
        """
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET calls = calls + 1 WHERE id = 1",
                SQL.identifier(DEDUP_LOCK_TABLE),
            )
        )

    @api.constrains("prospecting_fit_score")
    def _check_prospecting_fit_score(self):
        for lead in self:
            if not FIT_SCORE_MIN <= lead.prospecting_fit_score <= FIT_SCORE_MAX:
                raise ValidationError(
                    self.env._(
                        "The prospecting fit score must be between %(min)s and "
                        "%(max)s.",
                        min=FIT_SCORE_MIN,
                        max=FIT_SCORE_MAX,
                    )
                )

    @api.model
    def prospecting_create_lead(self, vals):
        """Create the lead in `vals` unless its person already has a lead in Odoo.

        A lead is one person at one company. The person already has a lead when any
        lead, in any campaign, open, lost or archived, shares their own email (a shared
        inbox identifies nobody), their LinkedIn profile, or their name at the same
        company, matched by CUIT, website or company name. Without a person, the lead
        is the company itself and any lead of that company matches. Another person at
        the same company is a new lead.

        The search reads every lead of the caller's companies, past the caller's own
        record rules, and answers only the matching lead's id. The caller must be able
        to create leads, and the lead is created with the caller's own permissions.

        Returns ``{"status": "created" | "duplicate", "lead_id": id}``.
        """
        self.check_access("create")
        self._prospecting_dedup_lock()
        duplicate = self._prospecting_duplicate(vals)
        if duplicate:
            return {"status": "duplicate", "lead_id": duplicate.id}
        lead = self.create([vals])
        return {"status": "created", "lead_id": lead.id}

    @api.model
    def _prospecting_duplicate(self, vals):
        """The oldest lead of the caller's companies that `vals` duplicates, if any."""
        company_keys = {
            "prospecting_cuit_key": cuit_key(vals.get("prospecting_cuit")),
            "prospecting_website_key": website_key(vals.get("website")),
            "prospecting_company_key": text_key(vals.get("partner_name")),
        }
        same_company = [
            Domain(name, "=", key) for name, key in company_keys.items() if key
        ]
        email = personal_email_key(vals.get("email_from"))
        linkedin = linkedin_key(vals.get("prospecting_linkedin"))
        contact = text_key(vals.get("contact_name"))

        if email or linkedin or contact:
            matches = []
            if email:
                matches.append(Domain("email_normalized", "=", email))
            if linkedin:
                matches.append(Domain("prospecting_linkedin_key", "=", linkedin))
            if contact and same_company:
                matches.append(
                    Domain("prospecting_contact_key", "=", contact)
                    & Domain.OR(same_company)
                )
        else:
            matches = same_company
        if not matches:
            return self.browse()
        domain = Domain(
            "company_id", "in", [*self.env.companies.ids, False]
        ) & Domain.OR(matches)
        found = (
            self.sudo()
            .with_context(active_test=False)
            .search(domain, order="id", limit=1)
        )
        return self.browse(found.ids)
