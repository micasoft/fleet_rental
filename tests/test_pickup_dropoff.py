import base64

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import FleetRentalCommon

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n')


@tagged('post_install', '-at_install', 'fleet_rental')
class TestPickupDropoff(FleetRentalCommon):
    """Pick-up and drop-off as the staff record them on their phone."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        me = cls.user_limited.partner_id
        cls.contract = cls.make_contract(cls, handle_pickup=me.id, handle_dropoff=me.id)
        cls.contract.action_confirm()

    def as_staff(self, records=None):
        return (records or self.contract).with_user(self.user_limited)

    def running(self, contract=None):
        contract = contract or self.contract
        contract.action_run()
        return contract

    # -- drop-off fields --------------------------------------------------------

    def test_dropoff_km_creates_odometer(self):
        self.contract.meters_dropoff_value = 12500
        odometer = self.contract.odometer_dropoff_id
        self.assertEqual(odometer.value, 12500)
        self.assertEqual(odometer.vehicle_id, self.contract.vehicle_id)
        self.contract.meters_dropoff_value = 12600
        self.assertEqual(self.contract.odometer_dropoff_id, odometer)
        self.assertEqual(odometer.value, 12600)

    def test_limited_can_write_dropoff_fields(self):
        self.running()
        attachment = self.env['ir.attachment'].with_user(self.user_limited).create(
            {'name': 'return.png', 'datas': PNG})
        values = {
            'meters_dropoff_value': 12500,
            'attachment_dropoff_ids': [Command.link(attachment.id)],
            'signature_dropoff': PNG,
        }
        for name, value in values.items():
            with self.subTest(field=name):
                self.as_staff().write({name: value})

    # -- complete pickup / drop-off -------------------------------------------

    def test_complete_pickup_starts_rental(self):
        staff = self.as_staff()
        staff.write({'meters_pickup_value': 12000, 'signature_pickup': PNG})
        staff.action_complete_pickup()
        self.assertEqual(self.contract.state, 'running')
        self.assertTrue(any('Pickup completed' in (m.body or '')
                            for m in self.contract.message_ids))

    def test_complete_pickup_requires_km_and_signature(self):
        staff = self.as_staff()
        with self.assertRaises(UserError):
            staff.action_complete_pickup()
        staff.meters_pickup_value = 12000
        with self.assertRaises(UserError):
            staff.action_complete_pickup()
        self.assertEqual(self.contract.state, 'reserved')

    def test_complete_pickup_wrong_state(self):
        draft = self.make_contract(vehicle_id=self.vehicle2.id,
                                   meters_pickup_value=12000, signature_pickup=PNG)
        with self.assertRaises(UserError):
            draft.action_complete_pickup()
        self.assertEqual(draft.state, 'draft')

    def test_complete_dropoff_moves_to_checking(self):
        self.contract.meters_pickup_value = 12000
        self.running()
        staff = self.as_staff()
        staff.meters_dropoff_value = 12400
        staff.action_complete_dropoff()
        self.assertEqual(self.contract.state, 'checking')

    def test_complete_dropoff_km_below_pickup_refused(self):
        self.contract.meters_pickup_value = 12000
        self.running()
        staff = self.as_staff()
        staff.meters_dropoff_value = 11000
        with self.assertRaises(UserError):
            staff.action_complete_dropoff()
        self.assertEqual(self.contract.state, 'running')

    def test_complete_pickup_other_handler_refused(self):
        other = self.make_contract(vehicle_id=self.vehicle2.id,
                                   handle_pickup=self.user_manager.partner_id.id,
                                   meters_pickup_value=12000, signature_pickup=PNG)
        other.action_confirm()
        with self.assertRaises(AccessError):
            self.as_staff(other).action_complete_pickup()
        self.assertEqual(other.state, 'reserved')

    def test_rental_user_can_complete(self):
        self.contract.write({'meters_pickup_value': 12000, 'signature_pickup': PNG})
        self.contract.with_user(self.user_normal).action_complete_pickup()
        self.assertEqual(self.contract.state, 'running')
