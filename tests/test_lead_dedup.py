# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from psycopg2.errors import SerializationFailure

from odoo import SUPERUSER_ID, api, sql_db
from odoo.exceptions import AccessError
from odoo.tests import BaseCase, TransactionCase, new_test_user, tagged
from odoo.tests.common import get_db_name
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestLeadDedup(TransactionCase):
    """`prospecting_create_lead`: one lead per person, never the same person twice."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Lead = cls.env["crm.lead"]
        cls.campaign = cls.env["utm.campaign"].create({"title": "Dedup campaign"})
        cls.other_campaign = cls.env["utm.campaign"].create({"title": "Other campaign"})
        cls.existing = cls.Lead.create(
            {
                "name": "Acme",
                "type": "lead",
                "partner_name": "Acme S.A.",
                "contact_name": "Agustín Pérez",
                "email_from": "Agustin.Perez@acme.com.ar",
                "prospecting_cuit": "30-71234567-8",
                "website": "https://www.acme.com.ar/",
                "prospecting_linkedin": "https://www.linkedin.com/in/agustin-perez/",
                "campaign_id": cls.other_campaign.id,
            }
        )

    def _lead(self, **values):
        return {
            "name": "Acme",
            "type": "lead",
            "campaign_id": self.campaign.id,
            **values,
        }

    def _count(self):
        return self.Lead.with_context(active_test=False).search_count([])

    def assertDuplicate(self, values, existing=None):
        before = self._count()
        result = self.Lead.prospecting_create_lead(values)
        self.assertEqual(
            result, {"status": "duplicate", "lead_id": (existing or self.existing).id}
        )
        self.assertEqual(self._count(), before, "a duplicate must create nothing")

    def assertCreated(self, values):
        before = self._count()
        result = self.Lead.prospecting_create_lead(values)
        self.assertEqual(result["status"], "created")
        lead = self.Lead.browse(result["lead_id"])
        self.assertTrue(lead.exists())
        self.assertEqual(self._count(), before + 1)
        return lead

    # Same person, by each key (S4), in another campaign (S3)

    def test_same_email_in_another_campaign_is_a_duplicate(self):
        self.assertDuplicate(
            self._lead(
                partner_name="Acme",
                contact_name="A. P.",
                email_from="agustin.perez@ACME.com.ar",
            )
        )

    def test_same_linkedin_profile_is_a_duplicate(self):
        self.assertDuplicate(
            self._lead(
                partner_name="Other name",
                contact_name="Agus",
                prospecting_linkedin="http://ar.linkedin.com/in/Agustin-Perez?trk=x",
            )
        )

    def test_same_name_at_the_same_company_by_cuit_is_a_duplicate(self):
        self.assertDuplicate(
            self._lead(
                partner_name="ACME Sociedad Anonima",
                contact_name="agustin  perez",
                prospecting_cuit="30712345678",
            )
        )

    def test_same_name_at_the_same_company_by_website_is_a_duplicate(self):
        self.assertDuplicate(
            self._lead(contact_name="Agustin Perez", website="acme.com.ar/contacto")
        )

    def test_same_name_at_the_same_company_by_name_is_a_duplicate(self):
        self.assertDuplicate(
            self._lead(partner_name="acme s.a.", contact_name="AGUSTÍN PÉREZ")
        )

    # Person B at company A is a new lead (S2)

    def test_another_person_at_the_same_company_is_created(self):
        lead = self.assertCreated(
            self._lead(
                partner_name="Acme S.A.",
                contact_name="Juana Gómez",
                email_from="juana.gomez@acme.com.ar",
                prospecting_cuit="30-71234567-8",
                website="https://acme.com.ar",
            )
        )
        self.assertEqual(lead.contact_name, "Juana Gómez")
        self.assertEqual(lead.campaign_id, self.campaign)

    def test_same_name_at_another_company_is_created(self):
        self.assertCreated(
            self._lead(
                partner_name="Globex",
                contact_name="Agustín Pérez",
                prospecting_cuit="30-79999999-1",
            )
        )

    def test_a_shared_inbox_identifies_nobody(self):
        self.existing.email_from = "info@acme.com.ar"
        self.assertCreated(
            self._lead(
                partner_name="Acme S.A.",
                contact_name="Juana Gómez",
                email_from="INFO@acme.com.ar",
            )
        )

    # Lost and archived leads, opportunities (S3)

    def test_an_archived_lost_opportunity_is_still_a_duplicate(self):
        self.existing.write({"type": "opportunity"})
        self.existing.action_set_lost()
        self.assertFalse(self.existing.active)
        self.assertDuplicate(
            self._lead(contact_name="X", email_from="agustin.perez@acme.com.ar")
        )

    # A lead without a contact is the company itself (S4)

    def test_a_company_without_contact_is_a_duplicate_when_the_company_exists(self):
        self.assertDuplicate(
            self._lead(partner_name="Unrelated", website="http://acme.com.ar")
        )

    def test_a_new_company_without_contact_is_created(self):
        self.assertCreated(
            self._lead(partner_name="Initech", website="https://initech.example")
        )

    # Elevated read for an own-documents user (S5)

    def test_an_own_documents_user_finds_another_salespersons_lead(self):
        owner = new_test_user(
            self.env, "dedup_owner", groups="sales_team.group_sale_salesman"
        )
        agent = new_test_user(
            self.env, "dedup_agent", groups="sales_team.group_sale_salesman"
        )
        self.existing.user_id = owner
        as_agent = self.Lead.with_user(agent)
        self.assertFalse(as_agent.search([("id", "=", self.existing.id)]))
        result = as_agent.prospecting_create_lead(
            self._lead(contact_name="Z", email_from="agustin.perez@acme.com.ar")
        )
        self.assertEqual(result, {"status": "duplicate", "lead_id": self.existing.id})

    def test_a_user_who_cannot_create_leads_learns_nothing(self):
        reader = new_test_user(self.env, "dedup_reader", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.Lead.with_user(reader).prospecting_create_lead(
                self._lead(email_from="agustin.perez@acme.com.ar")
            )

    def test_the_lead_is_created_with_the_callers_own_permissions(self):
        agent = new_test_user(
            self.env, "dedup_creator", groups="sales_team.group_sale_salesman"
        )
        result = self.Lead.with_user(agent).prospecting_create_lead(
            self._lead(partner_name="Initech", contact_name="Peter")
        )
        lead = self.Lead.browse(result["lead_id"])
        self.assertEqual(lead.create_uid, agent)

    # Keys that do not identify a company

    def test_a_malformed_stored_website_has_no_key(self):
        # Odoo refuses such a website on create; one already stored, as the upgrade
        # finds it, must not stop the keys from being computed.
        lead = self.Lead.create({"name": "Odd", "website": "https://odd.example"})
        self.env.cr.execute(
            "UPDATE crm_lead SET website = 'http://[bad' WHERE id = %s", [lead.id]
        )
        self.env.invalidate_all()
        lead._compute_prospecting_keys()
        self.assertFalse(lead.prospecting_website_key)

    def test_a_shared_platform_page_is_not_a_company(self):
        self.Lead.create(
            {
                "name": "Page",
                "partner_name": "Pagina",
                "website": "https://facebook.com/x",
            }
        )
        self.assertCreated(
            self._lead(partner_name="Otra", website="https://www.facebook.com/otra")
        )

    def test_a_company_without_contact_matches_by_cuit_alone(self):
        self.assertDuplicate(
            self._lead(partner_name="Renamed", prospecting_cuit="30712345678")
        )

    def test_leads_of_other_companies_are_not_searched(self):
        other = self.env["res.company"].create({"name": "Other company"})
        self.existing.company_id = other
        main_only = self.Lead.with_context(allowed_company_ids=[self.env.company.id])
        result = main_only.prospecting_create_lead(
            self._lead(contact_name="Z", email_from="agustin.perez@acme.com.ar")
        )
        self.assertEqual(result["status"], "created")

    # Normalized keys are stored for every lead

    def test_keys_follow_the_lead(self):
        self.assertEqual(self.existing.prospecting_cuit_key, "30712345678")
        self.assertEqual(self.existing.prospecting_website_key, "acme.com.ar")
        self.assertEqual(self.existing.prospecting_company_key, "acme s.a.")
        self.assertEqual(self.existing.prospecting_contact_key, "agustin perez")
        self.assertEqual(
            self.existing.prospecting_linkedin_key, "linkedin.com/in/agustin-perez"
        )
        self.existing.write({"prospecting_cuit": False, "website": False})
        self.assertFalse(self.existing.prospecting_cuit_key)
        self.assertFalse(self.existing.prospecting_website_key)


@tagged("post_install", "-at_install")
class TestLeadDedupConcurrency(BaseCase):
    """Two calls for the same person at once: the later one never creates a lead."""

    def test_a_call_whose_snapshot_misses_a_new_lead_is_cancelled(self):
        db = sql_db.db_connect(get_db_name())
        values = {
            "name": "Concurrent",
            "type": "lead",
            "partner_name": "Concurrent S.A.",
            "contact_name": "Rosa Díaz",
            "email_from": "rosa.diaz@concurrent.example",
        }
        created_id = None
        try:
            with db.cursor() as late_cr:
                late = api.Environment(late_cr, SUPERUSER_ID, {})["crm.lead"]
                # The late call's snapshot starts here, as an RPC request's would.
                late.search_count([])
                with db.cursor() as first_cr:
                    first = api.Environment(first_cr, SUPERUSER_ID, {})["crm.lead"]
                    result = first.prospecting_create_lead(dict(values))
                    self.assertEqual(result["status"], "created")
                    created_id = result["lead_id"]
                with (
                    mute_logger("odoo.sql_db"),
                    self.assertRaises(SerializationFailure),
                ):
                    late.prospecting_create_lead(dict(values))
                late_cr.rollback()
            with db.cursor() as retry_cr:
                retry = api.Environment(retry_cr, SUPERUSER_ID, {})["crm.lead"]
                self.assertEqual(
                    retry.prospecting_create_lead(dict(values)),
                    {"status": "duplicate", "lead_id": created_id},
                )
                retry_cr.rollback()
        finally:
            if created_id:
                with db.cursor() as cleanup_cr:
                    api.Environment(cleanup_cr, SUPERUSER_ID, {})["crm.lead"].browse(
                        created_id
                    ).unlink()
