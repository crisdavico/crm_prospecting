# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

FIT_SCORE_MIN = 0
FIT_SCORE_MAX = 100


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
