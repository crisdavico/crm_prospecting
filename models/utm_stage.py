# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import fields, models


class UtmStage(models.Model):
    """Campaign stages say which campaigns the prospecting agent may work on."""

    _inherit = "utm.stage"

    prospecting_enabled = fields.Boolean(
        string="Open for Prospecting",
        help="The prospecting agent only finds campaigns in stages with this "
        "option on.",
    )
