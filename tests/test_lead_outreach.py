# Copyright 2026 Seedian
# License AGPL-3.0-or-later (https://www.gnu.org/licenses/agpl-3.0.html).

from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.base.models.ir_mail_server import MailDeliveryException
from odoo.addons.mail.tests.common import MailCase


@tagged("post_install", "-at_install")
class TestLeadOutreach(MailCase):
    """What `prospecting_send_email` records on the lead besides the email."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bot = new_test_user(
            cls.env,
            "outreach_assistant",
            name="Outreach Assistant",
            email="outreach@seedian.example",
            groups="sales_team.group_sale_salesman_all_leads",
        )
        cls.Lead = cls.env["crm.lead"].with_user(cls.bot)
        Stage = cls.env["crm.stage"]
        cls.first_stage = cls.env["crm.lead"]._stage_find()
        cls.contacted = Stage.create(
            {
                "name": "Contacted",
                "sequence": cls.first_stage.sequence + 1,
                "prospecting_contacted": True,
            }
        )
        cls.later_stage = Stage.create({"name": "Proposal sent", "sequence": 50})

    def _lead(self, **vals):
        return self.env["crm.lead"].create(
            {
                "name": "Acme",
                "type": "lead",
                "contact_name": "Agustín Pérez",
                "email_from": "agustin.perez@acme.example",
                **vals,
            }
        )

    def _send(self, lead, subject="Hello", body="Hi there"):
        with self.mock_mail_gateway():
            return self.Lead.prospecting_send_email(lead.id, subject, body)

    # Outreach date (S1)

    def test_send_sets_the_outreach_date(self):
        lead = self._lead()
        self.assertFalse(lead.prospecting_outreach_date)
        self._send(lead)
        self.assertTrue(lead.prospecting_outreach_date)

    def test_duplicate_does_not_change_the_outreach_date(self):
        lead = self._lead()
        self._send(lead)
        lead.prospecting_outreach_date = "2026-01-02 03:04:05"
        result = self._send(lead)
        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(str(lead.prospecting_outreach_date), "2026-01-02 03:04:05")

    # Convert and move (S2)

    def test_lead_becomes_an_opportunity_in_contacted_without_a_partner(self):
        partners_before = self.env["res.partner"].search_count([])
        lead = self._lead()
        self._send(lead)
        self.assertEqual(lead.type, "opportunity")
        self.assertEqual(lead.stage_id, self.contacted)
        self.assertFalse(lead.partner_id)
        self.assertEqual(self.env["res.partner"].search_count([]), partners_before)

    def test_converted_lead_keeps_its_partner(self):
        partner = self.env["res.partner"].create(
            {"name": "Rosa Díaz", "email": "rosa.diaz@initech.example"}
        )
        lead = self._lead(partner_id=partner.id)
        self._send(lead)
        self.assertEqual(lead.type, "opportunity")
        self.assertEqual(lead.partner_id, partner)

    def test_first_stage_opportunity_moves_to_contacted(self):
        lead = self._lead(type="opportunity", stage_id=self.first_stage.id)
        self._send(lead)
        self.assertEqual(lead.stage_id, self.contacted)

    def test_opportunity_past_contacted_is_not_moved_back(self):
        lead = self._lead(type="opportunity", stage_id=self.later_stage.id)
        self._send(lead)
        self.assertEqual(lead.stage_id, self.later_stage)
        self.assertTrue(lead.prospecting_outreach_date)

    def test_failed_email_still_converts_moves_and_dates_the_lead(self):
        lead = self._lead()

        def _refuse(model, message, **kwargs):
            raise MailDeliveryException("Mailbox unavailable")

        with self.mock_mail_gateway():
            self.send_email_mocked.side_effect = _refuse
            result = self.Lead.prospecting_send_email(lead.id, "Hello", "Hi")
        status = self.Lead.prospecting_email_status(result["message_id"])
        self.assertEqual(status["status"], "failed")
        self.assertEqual(lead.type, "opportunity")
        self.assertEqual(lead.stage_id, self.contacted)
        self.assertTrue(lead.prospecting_outreach_date)

    def test_send_is_refused_without_a_contacted_stage(self):
        self.contacted.prospecting_contacted = False
        lead = self._lead()
        with self.assertRaisesRegex(UserError, "Contacted"):
            self._send(lead)
        self.assertFalse(self._mails)
        self.assertEqual(lead.type, "lead")
        self.assertFalse(lead.prospecting_outreach_date)

    # Views

    def test_stage_form_shows_the_contacted_flag(self):
        arch = self.env["crm.stage"].get_view(view_type="form")["arch"]
        self.assertIn('name="prospecting_contacted"', arch)

    def test_lead_form_shows_the_outreach_date(self):
        arch = self.env["crm.lead"].get_view(view_type="form")["arch"]
        self.assertIn('name="prospecting_outreach_date"', arch)
