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

To send a campaign's emails through a specific outgoing mail server, an administrator
picks it in the campaign's _Outgoing Mail Server_ field (_Prospecting_ tab, visible only
with Administration > Settings access). Servers that belong to a user are not offered.
Messages sent to the customer from the lead's chatter (_Send message_) or its full
composer go through that server too, unless the composer names another one; internal
notes do not. Without one, Odoo picks the server as for any other email. When the
server only accepts some senders (its _FROM Filtering_), Odoo rewrites the sender as it
always does.

A reply sent from a campaign lead's chatter keeps the customer's email thread: without
a subject of its own, it takes the subject of the lead's latest email or message, with
"Re: " in front when it does not start with it already, and the full composer suggests
that subject. Internal notes do not count. A lead without a campaign, or without any
email yet, keeps its name as the subject, as in Odoo.

To collect every reply to a campaign's leads in one mailbox, an administrator fills in
the campaign's _Reply-To_ (same tab, same access) with one email address. Every email on
its leads then asks replies to go there: the agent's emails and anything anyone sends
from the lead, from its chatter or its full composer. Set up an incoming mail server in
Odoo that fetches that mailbox, without a default model: replies land on the lead they
answer, and other mail there is left out. Use a mailbox of its own, not the sending
mailbox, so Odoo never reads a mailbox that a warm-up tool also uses. Without a
Reply-To, Odoo picks it as for any other lead. Odoo stores only the bare address.
Duplicating a campaign keeps its Reply-To only when an administrator duplicates it.

Mark one pipeline stage as _Contacted (Prospecting)_ in _CRM > Configuration > Stages_
(for a sales team with its own stages, mark one of them). When the agent emails a lead,
the lead becomes an opportunity, gets its _Outreach Date_ (in its _Prospecting_ tab) and,
if it is in the first stage of its team, moves to that stage. The agent cannot email
anyone until a stage is marked.
