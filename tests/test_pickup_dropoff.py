import base64

from odoo import Command
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
