Holds the context an AI prospecting agent reads from Odoo and the fields it fills on the
leads it finds.

- A **Prospecting Profile** model: for one product, the ideal customer profile and the
  buying signals, as plain text with one item per line.
- A **Prospecting** tab on the UTM campaign form with the brief the agent reads:
  profile, industry (the contacts' industry list), country, states, city, company size,
  target count and extra instructions.
- A **Prospecting** tab on the lead form with what the agent produces: fit score (0 to
  100), CUIT (used to detect duplicates) and the agent run reference. The agent's
  evidence for a lead goes in the lead's standard Notes (the `description` field).
