Everything lives under _CRM > Prospecting_, visible to sales users.

The module ships no products or profiles. Create each product you prospect for, with its
internal reference as a stable slug, and its prospecting profile in _CRM > Prospecting >
Profiles_. Sales managers edit the profiles; sales users can read them.

To brief the agent, open _CRM > Prospecting > Campaigns_, open a campaign, go to the
_Prospecting_ tab, pick a profile, an industry (the same list contacts use) and a
country, and fill in the target. With a country set, only that country's states can be
chosen. Campaigns can be searched by country and industry, and grouped by country.

The agent only works on campaigns whose stage is open for prospecting. _CRM >
Prospecting > Stages_ lists the campaign stages with their _Open for Prospecting_
option; stages start closed. Sales users can see the stages; changing them takes the
Administration > Settings access that Odoo requires for campaign stages. Leads
the agent creates are linked to the campaign and carry their fit score in the
_Prospecting_ tab of the lead; the agent's evidence goes in the lead's standard _Notes_
tab (the `description` field).

Before the email agent writes to a campaign's leads, fill in the campaign's _Email
Guidelines_ in its _Prospecting_ tab: the language to write in, the tone, the structure
and length, the call to action, what to avoid, example emails and any block to use word
for word. The agent emails no lead of a campaign without guidelines. Do not put an
opt-out line in the guidelines: it belongs in the sending user's signature, which every
email carries.

Mark one pipeline stage as _Contacted (Prospecting)_ in _CRM > Configuration > Stages_
(for a sales team with its own stages, mark one of them). When the agent emails a lead,
the lead becomes an opportunity, gets its _Outreach Date_ (in its _Prospecting_ tab) and,
if it is in the first stage of its team, moves to that stage. The agent cannot email
anyone until a stage is marked.
