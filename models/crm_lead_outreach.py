# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from collections import Counter

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from .crm_lead import personal_email_key

MAX_OUTREACH_COMPANIES = 10
"""Most companies one email agent run may write to."""

COMPANY_KEYS = (
    "prospecting_cuit_key",
    "prospecting_website_key",
    "prospecting_company_key",
)
"""Stored keys that say two leads are the same company, as in duplicate detection."""


class CrmLead(models.Model):
    """Who the email agent may write to, decided here and nowhere else."""

    _inherit = "crm.lead"

    @api.model
    def prospecting_outreach_candidates(
        self, campaign_id, limit=MAX_OUTREACH_COMPANIES
    ):
        """The companies of campaign `campaign_id` the email agent may write to.

        A lead qualifies when it is active, has an email, its address is not
        blacklisted and the agent never emailed it. A campaign without email
        guidelines offers nobody. Leads are grouped into companies by CUIT, website
        or company name, transitively, across every lead of the caller's companies in
        any campaign, archived ones included. A company is skipped when any of its
        leads was emailed by the agent, is won, or is an opportunity past the first
        stage of its team. Within a company, a person with their own email beats a
        shared inbox, which is offered only when the company has no one else.

        The grouping reads past the caller's record rules, but only leads the caller
        can read are offered. At most `limit` companies (1 to 10) are returned, best
        fit first.

        Returns ``{"campaign_id": id, "companies": [{"name": str, "people": [{
        "lead_id": id, "name": str, "job_title": str | False, "fit_score": int,
        "shared_inbox": bool}]}], "skipped_leads": {reason: count},
        "skipped_companies": {reason: count}}``. Lead reasons: ``inactive``,
        ``no_email``, ``blacklisted``, ``already_emailed``, ``shared_inbox``,
        ``campaign_without_guidelines``. Company reasons: ``already_emailed``,
        ``won``, ``opportunity_in_progress``.
        """
        if not 1 <= limit <= MAX_OUTREACH_COMPANIES:
            raise UserError(
                self.env._(
                    "The limit must be between 1 and %(max)s companies.",
                    max=MAX_OUTREACH_COMPANIES,
                )
            )
        campaign = self.env["utm.campaign"].browse(campaign_id).exists()
        if not campaign:
            raise UserError(
                self.env._("Campaign %(id)s does not exist.", id=campaign_id)
            )
        campaign.check_access("read")
        self.check_access("read")
        leads = self.with_context(active_test=False).search(
            [("campaign_id", "=", campaign.id)], order="id"
        )
        result = {
            "campaign_id": campaign.id,
            "companies": [],
            "skipped_leads": {},
            "skipped_companies": {},
        }
        if not (campaign.prospecting_email_guidelines or "").strip():
            if leads:
                result["skipped_leads"] = {"campaign_without_guidelines": len(leads)}
            return result

        skipped_leads = Counter()
        eligible = leads._prospecting_eligible_leads(skipped_leads)
        skipped_companies = Counter()
        companies = []
        for members in eligible._prospecting_companies():
            reason = members._prospecting_company_block()
            if reason:
                skipped_companies[reason] += 1
                continue
            people = members & eligible
            personal = people.filtered(
                lambda lead: personal_email_key(lead._prospecting_recipient_address())
            )
            if personal:
                skipped_leads["shared_inbox"] += len(people - personal)
                people = personal
            companies.append(
                people.sorted(lambda lead: (-lead.prospecting_fit_score, lead.id))
            )
        companies.sort(
            key=lambda people: (-people[0].prospecting_fit_score, min(people.ids))
        )
        result["companies"] = [
            people._prospecting_candidate_company() for people in companies[:limit]
        ]
        result["skipped_leads"] = dict(skipped_leads)
        result["skipped_companies"] = dict(skipped_companies)
        return result

    def _prospecting_eligible_leads(self, skipped):
        """These leads that qualify on their own, counting the others in `skipped`."""
        addresses = {lead.id: lead._prospecting_recipient_address() for lead in self}
        blacklisted = set(
            self.env["mail.blacklist"]
            .sudo()
            .search([("email", "in", [a for a in addresses.values() if a])])
            .mapped("email")
        )
        eligible = self.browse()
        for lead in self:
            address = addresses[lead.id]
            if not lead.active:
                skipped["inactive"] += 1
            elif not address:
                skipped["no_email"] += 1
            elif address in blacklisted:
                skipped["blacklisted"] += 1
            elif lead.prospecting_outreach_date:
                skipped["already_emailed"] += 1
            else:
                eligible |= lead
        return eligible

    def _prospecting_companies(self):
        """These leads grouped by company, each group with every lead of it.

        Two leads are the same company when they share any company key, directly or
        through other leads. Every lead of the caller's companies counts, in any
        campaign, archived included, read past record rules. Yields one recordset
        per company that holds at least one of these leads, in the caller's
        environment.
        """
        Lead = self.sudo().with_context(active_test=False)
        scope = Domain("company_id", "in", [*self.env.companies.ids, False])
        members = Lead.browse(self.ids)
        seen = {name: set() for name in COMPANY_KEYS}
        frontier = members
        while frontier:
            matches = []
            for name in COMPANY_KEYS:
                values = set(frontier.mapped(name)) - {False} - seen[name]
                seen[name] |= values
                if values:
                    matches.append(Domain(name, "in", list(values)))
            if not matches:
                break
            frontier = Lead.search(scope & Domain.OR(matches)) - members
            members |= frontier

        parent = {lead_id: lead_id for lead_id in members.ids}

        def root(lead_id):
            while parent[lead_id] != lead_id:
                parent[lead_id] = parent[parent[lead_id]]
                lead_id = parent[lead_id]
            return lead_id

        first_by_key = {}
        for lead in members:
            for name in COMPANY_KEYS:
                value = lead[name]
                if not value:
                    continue
                other = first_by_key.setdefault((name, value), lead.id)
                parent[root(lead.id)] = root(other)

        groups = {}
        for lead_id in members.ids:
            groups.setdefault(root(lead_id), []).append(lead_id)
        own = set(self.ids)
        for ids in groups.values():
            if own.intersection(ids):
                yield self.browse(ids)

    def _prospecting_company_block(self):
        """Why these leads, all of one company, block it; False when they do not.

        Reads past record rules: the caller may not see every lead of the company.
        """
        leads = self.sudo().with_context(active_test=False)
        if any(leads.mapped("prospecting_outreach_date")):
            return "already_emailed"
        if "won" in leads.mapped("won_status"):
            return "won"
        first_stages = {}
        for lead in leads.filtered(lambda lead: lead.type == "opportunity"):
            team = lead.team_id.id
            if team not in first_stages:
                first_stages[team] = lead._prospecting_first_stage()
            if lead.stage_id and lead.stage_id != first_stages[team]:
                return "opportunity_in_progress"
        return False

    def _prospecting_candidate_company(self):
        """These people of one company, best first, as the candidates list shows."""
        name = next(
            (lead.partner_name for lead in self if lead.partner_name),
            self[0].partner_id.commercial_company_name or self[0].name,
        )
        return {
            "name": name,
            "people": [
                {
                    "lead_id": lead.id,
                    "name": lead.contact_name
                    or lead.partner_id.name
                    or lead.partner_name
                    or lead.name,
                    "job_title": lead.function or False,
                    "fit_score": lead.prospecting_fit_score,
                    "shared_inbox": not personal_email_key(
                        lead._prospecting_recipient_address()
                    ),
                }
                for lead in self
            ],
        }
