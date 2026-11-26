from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestCalendar(FleetRentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].sudo().set_param('fleet_rental_calendar_sync', True)
        cls.pickup_partner = cls.user_limited.partner_id
        cls.dropoff_partner = cls.user_normal.partner_id

    def reserved(self, **vals):
        vals.setdefault('handle_pickup', self.pickup_partner.id)
        vals.setdefault('handle_dropoff', self.dropoff_partner.id)
        return self.confirm(self.make_contract(**vals))

    def test_reserve_creates_events(self):
        contract = self.reserved()
        pickup, dropoff = contract.calendar_start_date_id, contract.calendar_end_date_id
        start, end = datetime(2026, 3, 2, 10, 0), datetime(2026, 3, 5, 10, 0)
        self.assertEqual((pickup.start, pickup.stop), (start - timedelta(minutes=30), start))
        self.assertEqual((dropoff.start, dropoff.stop), (end - timedelta(minutes=30), end))
        self.assertLessEqual(contract.sales_person | self.pickup_partner, pickup.partner_ids)
        self.assertLessEqual(contract.sales_person | self.dropoff_partner, dropoff.partner_ids)

    def test_sync_off_no_events(self):
        self.env['ir.config_parameter'].sudo().set_param('fleet_rental_calendar_sync', False)
        contract = self.reserved()
        self.assertFalse(contract.calendar_start_date_id | contract.calendar_end_date_id)

    def test_dropoff_event_location(self):
        """The drop-off event is at the drop-off location."""
        contract = self.reserved()
        self.assertEqual(contract.calendar_end_date_id.location, 'Lisboa')

    def test_handler_change_updates_event(self):
        contract = self.reserved()
        new_handler = self.user_manager.partner_id
        contract.handle_dropoff = new_handler
        self.assertIn(new_handler, contract.calendar_end_date_id.partner_ids)

    def test_unchanged_resync_does_not_write(self):
        contract = self.reserved()
        CalendarEvent = type(self.env['calendar.event'])
        original_write = CalendarEvent.write
        calls = []

        def spy(records, vals):
            calls.append(vals)
            return original_write(records, vals)

        with patch.object(CalendarEvent, 'write', spy):
            contract.sync_calendar_end()
        self.assertFalse(calls)
