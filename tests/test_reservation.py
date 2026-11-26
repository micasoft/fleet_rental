import re
from datetime import datetime

from odoo.addons.mail.tests.common import MockEmail
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestReservation(FleetRentalCommon, MockEmail):

    def set_param(self, key, value):
        self.env['ir.config_parameter'].sudo().set_param(key, value)

    def mails_with_subject(self, prefix):
        return self._new_mails.filtered(lambda m: (m.subject or '').startswith(prefix))

    # -- confirm / availability --------------------------------------------

    def test_confirm_creates_reservation(self):
        contract = self.confirm(self.make_contract())
        self.assertEqual(contract.state, 'reserved')
        reservation = self.vehicle.rental_reserved_time
        self.assertEqual(len(reservation), 1)
        self.assertEqual(reservation, contract.reserved_fleet_id)
        self.assertEqual(reservation.date_from, contract.rent_start_date)
        self.assertEqual(reservation.date_to, contract.rent_end_date)

    def test_confirm_assigns_number(self):
        """Confirmed contracts of any company get a number from the shared sequence."""
        contract = self.confirm(self.make_contract())
        self.assertRegex(contract.name or '', r'^RENT/%d/\d{4}$' % contract.create_date.year)

    def test_overlap_refused(self):
        self.confirm(self.make_contract())
        other = self.make_contract(rent_start_date='2026-03-04 10:00:00',
                                   rent_end_date='2026-03-06 10:00:00')
        with self.assertRaises(UserError):
            other.action_confirm()

    def test_adjacent_allowed(self):
        self.confirm(self.make_contract())
        other = self.confirm(self.make_contract(rent_start_date='2026-03-06 10:00:00',
                                                rent_end_date='2026-03-08 10:00:00'))
        self.assertEqual(other.state, 'reserved')

    def test_same_time_handover_allowed(self):
        """Returned at 10:00, next customer picks up at 10:00: no overlap."""
        self.confirm(self.make_contract())
        other = self.confirm(self.make_contract(rent_start_date='2026-03-05 10:00:00',
                                                rent_end_date='2026-03-07 10:00:00'))
        self.assertEqual(other.state, 'reserved')

    def test_number_kept_after_back_to_quote(self):
        """Back to Quote and confirmed again keeps the contract number."""
        contract = self.confirm(self.make_contract())
        number = contract.name
        self.assertTrue(number)
        contract.action_move_to_quote()
        contract.action_confirm()
        self.assertEqual(contract.name, number)

    def test_cancel_cleans_up(self):
        self.set_param('fleet_rental_calendar_sync', True)
        contract = self.confirm(self.make_contract())
        events = contract.calendar_start_date_id | contract.calendar_end_date_id
        self.assertEqual(len(events), 2)
        contract.action_cancel()
        self.assertEqual(contract.state, 'cancel')
        self.assertFalse(self.vehicle.rental_reserved_time)
        self.assertFalse(events.exists())
        self.assertEqual(self.vehicle.state_id, self.env.ref('fleet_rental.vehicle_state_active'))

    # -- mails --------------------------------------------------------------

    def test_booking_mail_when_enabled(self):
        self.set_param('fleet_rental_send_booking', True)
        with self.mock_mail_gateway():
            self.confirm(self.make_contract())
        mails = self.mails_with_subject('Reservation for')
        self.assertEqual(len(mails), 1)
        self.assertIn(self.customer, mails.recipient_ids)

    def test_no_booking_mail_when_disabled(self):
        with self.mock_mail_gateway():
            self.confirm(self.make_contract())
        self.assertFalse(self.mails_with_subject('Reservation for'))

    def test_send_quote(self):
        contract = self.make_contract()
        with self.mock_mail_gateway():
            contract.action_send_quote()
        self.assertTrue(contract.sent_quote)
        self.assertEqual(len(self.mails_with_subject('Renting quote for')), 1)

    def test_send_quote_vehicle_booked(self):
        self.confirm(self.make_contract())
        with self.assertRaises(UserError):
            self.make_contract().action_send_quote()

    # -- extension ----------------------------------------------------------

    def extend(self, contract, new_end):
        contract.action_extend_rent()
        contract.rent_end_date = new_end
        contract.action_confirm_extend_rent()

    def test_extend_requires_later_date(self):
        contract = self.confirm(self.make_contract())
        contract.action_extend_rent()
        with self.assertRaises(ValidationError):
            contract.rent_end_date = datetime(2026, 3, 4, 10, 0)

    def test_extend_updates_reservation(self):
        contract = self.confirm(self.make_contract())
        self.extend(contract, datetime(2026, 3, 7, 10, 0))
        self.assertEqual(contract.reserved_fleet_id.date_to, datetime(2026, 3, 7, 10, 0))
        self.assertFalse(contract.read_only)

    def test_extend_discard_restores(self):
        contract = self.confirm(self.make_contract())
        contract.action_extend_rent()
        contract.rent_end_date = datetime(2026, 3, 7, 10, 0)
        contract.action_discard_extend()
        self.assertEqual(contract.rent_end_date, datetime(2026, 3, 5, 10, 0))
        self.assertFalse(contract.read_only)

    def test_extend_into_other_reservation_refused(self):
        """Extending into another reservation of the vehicle is refused."""
        contract = self.confirm(self.make_contract())
        self.confirm(self.make_contract(rent_start_date='2026-03-06 10:00:00',
                                        rent_end_date='2026-03-08 10:00:00'))
        with self.assertRaises(UserError):
            self.extend(contract, datetime(2026, 3, 7, 10, 0))

    def test_extend_reprices_rent(self):
        """Extending re-prices the rent: 3 days at 50 = 150; extended to 5 days the 4-10 range applies: 5 x 40."""
        contract = self.confirm(self.make_contract())
        self.extend(contract, datetime(2026, 3, 7, 10, 0))
        self.assertEqual(contract.rent_cost, 200)
