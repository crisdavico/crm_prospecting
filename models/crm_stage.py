# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import fields, models


class CrmStage(models.Model):
    """The pipeline stage a lead moves to when the agent emails it."""

    _inherit = "crm.stage"

    prospecting_contacted = fields.Boolean(
        string="Contacted (Prospecting)",
        help="A lead the email agent writes to moves to this stage, if it is in the "
        "first stage of its sales team. With several stages marked, the first one of "
        "the lead's team is used.",
    )
