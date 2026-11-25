# crm_prospecting — email outreach (PLAN.md CP-1…CP-7)

Objective: give `crm_prospecting` what the email writer agent needs (outreach date,
convert/move on send, campaign email guidelines, candidates/detail/brief methods). Repo:
`odoo/custom/src/crisdavico/crm_prospecting` (own git repo), branch
`feat/email-outreach` from `origin/main` (c49c3ca). Delivery: ask-on-risk. Runner:
`invoke test -m crm_prospecting` from the seedian root. Source plan:
`/home/crisd/projects/seedian/agents/email-writer-agent/PLAN.md` (decisions D1–D24,
tasks CP-1…CP-7).

## Specs

- **S1 (CP-1, D22)** "Add a field on the lead recording when the agent last emailed it
  (proposal: `prospecting_outreach_date`). `prospecting_send_email` sets it." Check:
  "after a send the field is set; a `duplicate` answer does not change it."
- **S2 (CP-2, D22)** "In the same transaction as the email: a record of type lead
  becomes an opportunity; a lead or first-stage opportunity moves to Contacted; a later
  stage is left alone; no partner is created." Check: "one test per case, including
  "already past Contacted is not moved back" and "no `res.partner` created"."
  - Decision (user, 2026-11-16): Contacted is a boolean flag on `crm.stage`; if no stage
    is flagged, the send is refused with a clear error. "First stage" is the
    lowest-sequence stage of the lead's sales team (Odoo's `_stage_find`).
  - Verified: `crm.lead.convert_opportunity(partner)` creates no partner, but an empty
    `partner` clears an existing `partner_id`, so it is called with `lead.partner_id`.
  - Assumption: a record is moved only when it has no stage or is in the first stage;
    any other stage is left alone, for leads too.
- **S3 (CP-3, D16)** "Add a text field on the campaign's Prospecting tab (proposal:
  `prospecting_email_guidelines`) for language, tone, structure, call to action, things
  to avoid, example emails and word-for-word blocks." Check: "field is editable in the
  form and documented in `readme/`."
- **S4 (CP-4, D8–D11, D13)** "A method that, for one campaign and a limit, returns
  eligible companies with their people and the skip counts by reason. It groups by the
  existing company keys." Check: "one test per rule: inactive, no email, blacklisted,
  already emailed, campaign without guidelines, company already emailed, company with an
  opportunity past the first stage, company won, shared inbox only when no person
  exists, limit respected."
  - People carry: lead id, name, job title, fit score, shared-inbox flag (PLAN.md tool
    table). Limit max 10.
  - Verified: `crm.lead` has `is_blacklisted` (from `mail.thread.blacklist`,
    searchable).
  - Transitive grouping: companies are connected components over CUIT, website and
    company keys, expanded across all leads of the caller's companies (any campaign,
    archived included), so A–B (CUIT) and B–C (website) make one company.
  - Decision (user, 2026-11-16, L8): a lost (archived) opportunity does not block its
    company; only an active opportunity past the first stage does. Emailed and won leads
    block, archived or not; the lookup reads past record rules, like
    `_prospecting_duplicate`, and returns only leads the caller can read.
- **S5 (CP-5, D15)** "A method returning the writing detail of one lead." Fields
  (PLAN.md): "contact and company names, job title, evidence, website, LinkedIn, notes,
  country". Check: "refuses a lead the caller cannot read; returns no field the draft
  does not need."
  - Evidence and notes are the same field (`description`, per `readme/USAGE.md`),
    returned as plain text.
  - Implemented as `crm.lead.prospecting_outreach_detail(lead_id)`.
- **S6 (CP-6)** "A method returning the campaign's profile, goal and guidelines."
  Profile: "product, description, ICP, buying signals". Check: "answers "no guidelines"
  clearly rather than an empty brief."
  - Implemented as `utm.campaign.prospecting_outreach_brief(campaign_id)`; "no
    guidelines" is a `UserError` naming the campaign (parent's choice).
- **S7 (CP-7)** "Update `readme/`, the manifest version and a migration if the new
  fields need one."
  - Version 19.0.1.4.0. No migration: new columns start empty/false. i18n (`es_AR.po`,
    `.pot`) not regenerated: follow-up.

## Tasks

| ID  | Specs  | Route  | Status                               | Commit                                                |
| --- | ------ | ------ | ------------------------------------ | ----------------------------------------------------- |
| T1  | S1, S2 | inline | done (RED→GREEN observed)            | d31c8f7, b4739d2 (advisory fix)                       |
| T2  | S3     | inline | done (RED→GREEN observed)            | e8ba212                                               |
| T3  | S4     | inline | done (RED→GREEN observed)            | 2929c9d, 334ca11 (advisory fix), 1ecd6f7 (lost deals) |
| T4  | S5, S6 | inline | done (RED→GREEN observed)            | 88081ac                                               |
| T5  | S7     | inline | done (structural: suite + rst check) | d8fdc70                                               |

Route evidence: one understood addon, writes run inline (no parallel units with disjoint
surfaces; T3 depends on T1's field and stage flag). Risk: T3/T4 read past record rules →
high-risk item 2, independent verifier at feature end.

## Log

- **L1 (2026-11-16, user):** "I want to start with PLAN.md" → chose "crm_prospecting
  (Recommended)".
- **L2 (2026-11-16, user):** Contacted stage → "Flag on crm.stage (Recommended)".
- **L3:** Forecast ≈ 900 authored lines (> 400): chain strategy to be asked before the
  first commit. Engram mirror pending: no memory tools in this session.
- **L4 (2026-11-16, user):** chain strategy → "stacked-to-main". Slices: PR1 =
  d31c8f7..e8ba212 (T1, fix, T2), PR2 = 2929c9d..334ca11 (T3, fix), PR3 =
  88081ac..d8fdc70 (T4, T5).
- **L5:** Native review. T1 escalated item 2 (write-access guard): granted, approved,
  acknowledged; advisory R3-dup-precheck fixed in b4739d2, R3-cross-team-stage rejected
  (`_convert_opportunity_data` sets a stage only when missing). Slice d31c8f7..2929c9d
  escalated item 2 (sudo grouping): granted, approved, acknowledged;
  R3-archived-blacklist fixed in 334ca11, limit type checked; R1-001 (skip counts reveal
  blocks caused by unreadable leads) left as documented behaviour, reported to the user.
  Slice 2929c9d..d8fdc70: under budget, no review due.
- **L6:** Checks:
  `docker compose run --rm odoo odoo --test-enable -u crm_prospecting --test-tags /crm_prospecting`
  → 111 tests, 0 failed. ruff 0.13.0 clean on changed files (2 pre-existing E501 in
  tests/test_prospecting_fields.py). README.rst validated with docutils.
- **L7:** Independent verifier (feature end, item 2): S1–S7 pass, no blockers; 16
  scratch probes + 111 suite tests passed (127). Advisories: lost opportunities past
  first stage block their company forever as `opportunity_in_progress` (open question
  for the user); shared inbox offered when the only person is unreachable; grouping can
  link readable leads through an unreadable one; unreadable partner raises AccessError
  (pre-existing pattern); deploy must flag a Contacted stage. Scratch removed.
- **L8 (2026-11-16, user):** lost deals → "Ignore lost deals (Recommended)". S4 updated;
  T3 reopened and closed in 1ecd6f7 (RED→GREEN observed, suite 112 tests, 0 failed).
  Assessment 2929c9d..HEAD: under budget, no review due. Slice PR3 now =
  88081ac..1ecd6f7.
- **L9 (2026-11-16, user):** "push and open the three PRs" → #5 (send-side, base main),
  #6 (candidates, base #5, 539 lines: size exception recommended), #7
  (brief/detail/docs, base #6).
