# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.tools import sql


def migrate(cr, version):
    """Keep the campaign instructions as the campaign goal.

    `prospecting_instructions` became `prospecting_goal`. Renaming the column before
    the registry loads keeps its values; Odoo then removes the old field's metadata
    and finds no column left to drop.
    """
    if sql.column_exists(cr, "utm_campaign", "prospecting_instructions") and not (
        sql.column_exists(cr, "utm_campaign", "prospecting_goal")
    ):
        sql.rename_column(cr, "utm_campaign", "prospecting_instructions", "prospecting_goal")
