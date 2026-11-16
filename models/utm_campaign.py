# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


def text_lines(value):
    """The non-blank lines of `value`, stripped."""
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class UtmCampaign(models.Model):
    """The brief the prospecting agent reads before looking for leads."""

    _inherit = "utm.campaign"

    prospecting_profile_id = fields.Many2one(
        comodel_name="prospecting.profile",
        help="Product and ideal customer profile this campaign prospects for.",
    )
    prospecting_industry_id = fields.Many2one(
        comodel_name="res.partner.industry",
        help="Industry of the companies to look for, as set on contacts.",
    )
    prospecting_country_id = fields.Many2one(
        comodel_name="res.country",
        help="Country where the companies should be.",
    )
    prospecting_state_ids = fields.Many2many(
        comodel_name="res.country.state",
        relation="utm_campaign_prospecting_state_rel",
        column1="campaign_id",
        column2="state_id",
        string="Prospecting States",
        help="States or provinces where the companies should be.",
    )
    prospecting_city = fields.Char(
        help="City where the companies should be.",
    )
    prospecting_company_size = fields.Char(
        help="Size of the companies to look for, for example by employee count.",
    )
    prospecting_target_count = fields.Integer(
        help="How many leads the agent should find for this campaign.",
    )
    prospecting_goal = fields.Text(
        help="What this campaign aims to achieve. The agent reads it to focus its lead "
        "search.",
    )
    prospecting_email_guidelines = fields.Text(
        string="Email Guidelines",
        help="How the email agent writes to this campaign's leads: language, tone, "
        "structure, call to action, things to avoid, example emails and blocks to use "
        "word for word. Without guidelines the agent emails none of its leads.",
    )

    @api.model
    def prospecting_outreach_brief(self, campaign_id):
        """What the email agent reads once before writing to campaign `campaign_id`.

        Refuses a campaign without email guidelines, since the agent writes to none
        of its leads. The ideal customer profile and buying signals are lists, one
        item per line of the profile.

        Returns ``{"campaign_id": id, "name": str, "goal": str | False,
        "email_guidelines": str, "profile": {"product": str, "description": str |
        False, "icp": [str], "buying_signals": [str]} | False}``.
        """
        campaign = self.browse(campaign_id).exists()
        if not campaign:
            raise UserError(
                self.env._("Campaign %(id)s does not exist.", id=campaign_id)
            )
        campaign.check_access("read")
        guidelines = (campaign.prospecting_email_guidelines or "").strip()
        if not guidelines:
            raise UserError(
                self.env._(
                    "Campaign %(name)s has no email guidelines: no email is written "
                    "for its leads. Fill them in on the campaign's Prospecting tab.",
                    name=campaign.display_name,
                )
            )
        profile = campaign.prospecting_profile_id
        return {
            "campaign_id": campaign.id,
            "name": campaign.title or campaign.display_name,
            "goal": campaign.prospecting_goal or False,
            "email_guidelines": guidelines,
            "profile": {
                "product": profile.product_id.display_name,
                "description": profile.description or False,
                "icp": text_lines(profile.icp),
                "buying_signals": text_lines(profile.buying_signals),
            }
            if profile
            else False,
        }

    @api.constrains("prospecting_country_id", "prospecting_state_ids")
    def _check_prospecting_states_country(self):
        for campaign in self:
            country = campaign.prospecting_country_id
            if not country:
                continue
            foreign = campaign.prospecting_state_ids.filtered(
                lambda state, country=country: state.country_id != country
            )
            if foreign:
                raise ValidationError(
                    self.env._(
                        "The prospecting states of campaign %(campaign)s must belong "
                        "to %(country)s. These do not: %(states)s.",
                        campaign=campaign.display_name,
                        country=country.name,
                        states=", ".join(foreign.mapped("name")),
                    )
                )
