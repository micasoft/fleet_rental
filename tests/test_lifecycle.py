from datetime import date

from freezegun import freeze_time

from odoo import fields
from odoo.addons.mail.tests.common import MockEmail
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestLifecycle(FleetRentalCommon, MockEmail):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.share_sequence()
        cls.state_rent = cls.env.ref('fleet_rental.vehicle_state_rent')
        cls.state_active = cls.env.ref('fleet_rental.vehicle_state_active')

    def cron_model(self):
        return self.env['car.rental.contract'].with_user(self.env.ref('base.user_root'))

    def reserved(self, **vals):
        return self.confirm(self.make_contract(**vals))

    def mails_with_subject(self, prefix):
        return self._new_mails.filtered(lambda m: (m.subject or '').startswith(prefix))

    # -- vehicle state --------------------------------------------------------

    def test_running_sets_vehicle_rent(self):
        contract = self.reserved()
        contract.action_run()
        self.assertEqual(self.vehicle.state_id, self.state_rent)

    def test_cancel_and_invoice_set_vehicle_active(self):
        for final_state in ('cancel', 'invoice'):
            with self.subTest(state=final_state):
                contract = self.reserved()
                contract.action_run()
                contract.state = final_state
                self.assertEqual(self.vehicle.state_id, self.state_active)
                contract.reserved_fleet_id.unlink()

    # -- fleet_scheduler ------------------------------------------------------

    def test_scheduler_reserved_to_running(self):
        contract = self.reserved()
        with freeze_time('2026-03-02 12:00:00'):
            self.cron_model().fleet_scheduler()
        self.assertEqual(contract.state, 'running')

    def test_scheduler_running_to_checking(self):
        contract = self.reserved()
        contract.action_run()
        with freeze_time('2026-03-06 12:00:00'):
            self.cron_model().fleet_scheduler()
        self.assertEqual(contract.state, 'checking')

    def test_scheduler_end_today_stays_running(self):
        contract = self.reserved()
        contract.action_run()
        with freeze_time('2026-03-05 12:00:00'):
            self.cron_model().fleet_scheduler()
        self.assertEqual(contract.state, 'running')

    def test_scheduler_invoice_to_done(self):
        contract = self.reserved()
        contract.state = 'invoice'
        with freeze_time('2026-03-06 12:00:00'):
            self.cron_model().fleet_scheduler()
        self.assertEqual(contract.state, 'done')

    def test_scheduler_uses_local_date(self):
        """Bug: the cron uses the UTC date, not the company's local date.

        23:15 UTC on 14 July is 00:15 on 15 July in Lisbon: a rental starting
        at 09:00 local on 15 July starts today."""
        contract = self.reserved(rent_start_date='2026-07-15 08:00:00',
                                 rent_end_date='2026-07-18 08:00:00')
        with freeze_time('2026-07-14 23:15:00'):
            self.cron_model().fleet_scheduler()
        self.assertEqual(contract.state, 'running')

    # -- next_event -----------------------------------------------------------

    def test_next_event_pickup_tomorrow(self):
        contract = self.reserved()
        with freeze_time('2026-03-01 12:00:00'), self.mock_mail_gateway():
            self.cron_model().next_event()
        mails = self.mails_with_subject('Next events for %s!' % contract.name)
        self.assertEqual(len(mails), 1)
        self.assertIn(contract.handle_pickup, mails.recipient_ids)

    def test_next_event_dropoff_tomorrow(self):
        contract = self.reserved()
        contract.action_run()
        with freeze_time('2026-03-04 12:00:00'), self.mock_mail_gateway():
            self.cron_model().next_event()
        mails = self.mails_with_subject('Next events for %s!' % contract.name)
        self.assertEqual(len(mails), 1)
        self.assertIn(contract.handle_dropoff, mails.recipient_ids)

    def test_next_event_uses_local_tomorrow(self):
        """Bug: the cron uses the UTC date, not the company's local date.

        At 00:15 local on 15 July, a pickup on 16 July is tomorrow."""
        contract = self.reserved(rent_start_date='2026-07-16 08:00:00',
                                 rent_end_date='2026-07-18 08:00:00')
        with freeze_time('2026-07-14 23:15:00'), self.mock_mail_gateway():
            self.cron_model().next_event()
        self.assertEqual(len(self.mails_with_subject('Next events for %s!' % contract.name)), 1)

    def test_next_event_changes_no_state(self):
        contract = self.reserved()
        with freeze_time('2026-02-25 12:00:00'):
            self.cron_model().next_event()
        self.assertEqual(contract.state, 'reserved')

    # -- defaults and several records ----------------------------------------

    def test_defaults_use_creation_date(self):
        """Bug: date defaults are fixed when the server starts (default=str(date.today()))."""
        names = ['rent_start_date', 'rent_pickup_date', 'rent_dropoff_date']
        with freeze_time('2030-01-15 10:00:00'):
            defaults = self.env['car.rental.contract'].default_get(names)
        for name in names:
            with self.subTest(field=name):
                self.assertEqual(fields.Datetime.to_datetime(defaults[name]).date(), date(2030, 1, 15))

    def test_write_state_on_two_contracts(self):
        """Bug: the state constraint assumes one record (fails on several)."""
        c1 = self.reserved()
        c2 = self.reserved(vehicle_id=self.vehicle2.id)
        (c1 | c2).write({'state': 'running'})
        self.assertEqual((self.vehicle | self.vehicle2).state_id, self.state_rent)

    def test_cancel_two_contracts(self):
        """Bug: action_cancel assumes one record (fails on several)."""
        c1 = self.reserved()
        c2 = self.reserved(vehicle_id=self.vehicle2.id)
        (c1 | c2).action_cancel()
        self.assertEqual(set((c1 | c2).mapped('state')), {'cancel'})
