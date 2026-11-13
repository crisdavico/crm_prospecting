# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import fields, models


class ProspectingProfile(models.Model):
    """Who to look for when prospecting for one product.

    The description says in free text what the profile is. The ideal customer
    profile and the buying signals are plain text with one item per line, so
    the prospecting agent can split them into lists.
    """

    _name = "prospecting.profile"
    _description = "Prospecting Profile"
    _order = "name, id"

    name = fields.Char(required=True)
    product_id = fields.Many2one(
        comodel_name="product.template",
        string="Product",
        required=True,
        index=True,
    )
    description = fields.Text(
        help="What this profile is: the segment or angle it covers for the product.",
    )
    icp = fields.Text(
        string="Ideal Customer Profile",
        help="Who the product is for. One item per line.",
    )
    buying_signals = fields.Text(
        help="Public signs that a company may need the product. One item per line.",
    )
    active = fields.Boolean(default=True)
