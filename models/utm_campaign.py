# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import fields, models


class UtmCampaign(models.Model):
    """The brief the prospecting agent reads before looking for leads."""

    _inherit = "utm.campaign"

    prospecting_profile_id = fields.Many2one(
        comodel_name="prospecting.profile",
        help="Product and ideal customer profile this campaign prospects for.",
    )
    prospecting_industry = fields.Char(
        help="Industry or sector of the companies to look for.",
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
