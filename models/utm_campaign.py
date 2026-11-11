# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    prospecting_instructions = fields.Text(
        help="Extra instructions and exclusions for the agent.",
    )

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
