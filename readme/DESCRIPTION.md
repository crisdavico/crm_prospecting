Holds the context an AI prospecting agent reads from Odoo and the fields it fills on the
leads it finds.

- A **Prospecting Profile** model: for one product, a free-text description of what the
  profile is, plus the ideal customer profile and the buying signals, as plain text with
  one item per line.
- A **Prospecting** tab on the UTM campaign form with the brief the agent reads:
  profile, industry (the contacts' industry list), country, states, city, company size,
  target count and the campaign goal, which focuses the agent's lead search.
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
  email-less leads are refused. The same subject and body sent to the lead in the last
  24 hours is not sent again unless it failed. It answers
  `{"status": "queued" | "duplicate", "message_id": id, "email": address}`;
  `crm.lead.prospecting_email_status(message_id)` then answers `"sent"` once the SMTP
  server accepted it, `"failed"` with a `failure_reason`, or `"pending"`.
