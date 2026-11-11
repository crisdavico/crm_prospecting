# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

{
    "name": "CRM Prospecting",
    "version": "19.0.1.0.0",
    "category": "Sales/CRM",
    "summary": "Product profiles, campaign briefs and lead fields for an AI "
    "prospecting agent",
    "author": "Eynes, Seedian",
    "website": "https://seedian.ai",
    "depends": ["crm", "product"],
    "data": [
        "security/ir.model.access.csv",
        "views/prospecting_profile_views.xml",
        "views/utm_campaign_views.xml",
        "views/utm_stage_views.xml",
        "views/crm_lead_views.xml",
        "views/crm_prospecting_menus.xml",
    ],
    "installable": True,
    "application": False,
    "license": "AGPL-3",
}
