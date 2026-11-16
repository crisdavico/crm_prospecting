Holds the context an AI prospecting agent reads from Odoo and the fields it fills on the
leads it finds.

- A **Prospecting Profile** model: for one product, a free-text description of what the
  profile is, plus the ideal customer profile and the buying signals, as plain text with
  one item per line.
- A **Prospecting** tab on the UTM campaign form with the brief the agent reads:
  profile, industry (the contacts' industry list), country, states, city, company size,
  target count and the campaign goal, which focuses the agent's lead search. The tab
  also holds the campaign's **Email Guidelines**, which tell the email agent how to
  write to the campaign's leads: language, tone, structure, call to action, things to
  avoid, example emails and blocks to use word for word.
- An **Open for Prospecting** option on campaign stages: the agent only works on
  campaigns in stages where it is on.
- A **Prospecting** tab on the lead form with what the agent produces: fit score (0 to
  100), CUIT and LinkedIn profile (both used to detect duplicates) and the agent run
  reference. The agent's evidence for a lead goes in the lead's standard Notes (the
  `description` field).
- **Duplicate detection** for the agent: `crm.lead.prospecting_create_lead(vals)`
  creates the lead unless its person already has one, and answers
  `{"status": "created" | "duplicate", "lead_id": id}`. A lead is one person at one
  company: the same person is their own email (a shared inbox such as `info@` identifies
  nobody), their LinkedIn profile, or their name at the same company, matched by CUIT,
  website or company name, ignoring case and accents. Every lead and opportunity counts,
  in any campaign, including lost and archived ones. Another person at the same company
  is a new lead. A lead without a person is the company itself. The search reads past
  the caller's record rules but answers only the matching lead's id; the caller must be
  able to create leads, and creates with their own permissions.
- **Customer emails** for the agent:
  `crm.lead.prospecting_send_email(lead_id, subject, body)` sends one email to the
  lead's customer and logs it on the lead's chatter. It goes to the lead's contact when
  it has an email, otherwise to the lead's own email without creating a contact. The
  body is plain text: it is escaped and its line breaks kept. The email is authored by
  the caller, with their signature, and sent right after the request commits; internal
  followers get their usual notification, customer followers nothing. Lost, archived and
  email-less leads are refused. The same subject and body sent to the same address of
  the lead in the last 24 hours is not sent again unless it failed. It answers
  `{"status": "queued" | "duplicate", "message_id": id, "email": address}`;
  `crm.lead.prospecting_email_status(message_id)` then answers `"sent"` once the SMTP
  server accepted it, `"failed"` with a `failure_reason`, or `"pending"`.
  The caller needs write access to the lead, because in the same transaction, before
  the email is known to be sent, the lead gets its **Outreach Date**, a lead becomes an
  opportunity without creating a contact, and a lead without a stage or in the first
  stage of its sales team moves to the pipeline stage marked **Contacted
  (Prospecting)**. Later stages are left alone. Without a stage marked Contacted the
  email is refused. A duplicate changes nothing. A failed email leaves these changes in
  place.
- **Outreach** for the email agent, which holds every rule of who may be emailed:
  `crm.lead.prospecting_outreach_candidates(campaign_id, limit)` lists up to `limit`
  (1 to 10) companies of the campaign, best fit first, each with the people the agent
  may write to (lead id, name, job title, fit score and whether the address is a shared
  inbox), plus counts of skipped leads and companies by reason. A lead qualifies when it
  is active, has an email, its address is not blacklisted and the agent never emailed
  it, in a campaign with email guidelines. Leads are grouped into companies by CUIT,
  website or company name, also through other leads, across every lead in any campaign,
  lost and archived ones included. A company is skipped when any of its leads was
  emailed by the agent, is won, or is an opportunity past the first stage of its team. A
  shared inbox is offered only when the company has no one else. The grouping reads
  past the caller's record rules: only leads the caller can read are offered, but the
  skip counts can reflect leads the caller cannot read.
  `utm.campaign.prospecting_outreach_brief(campaign_id)` answers the campaign's profile
  (product, description, and the ideal customer profile and buying signals as lists),
  goal and email guidelines, and refuses a campaign without guidelines.
  `crm.lead.prospecting_outreach_detail(lead_id)` answers what a draft to one lead
  needs: contact and company names, job title, evidence (the lead's notes as plain
  text), website, LinkedIn and country, for a lead the caller can read.
