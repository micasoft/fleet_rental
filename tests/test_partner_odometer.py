from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestPartnerOdometer(FleetRentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.share_sequence()

    def test_write_two_partners(self):
        """Bug: res.partner.write assumes one partner (fails on several)."""
        self.env['ir.config_parameter'].sudo().set_param('fleet_rental_calendar_sync', True)
        contract = self.confirm(self.make_contract())
        (self.customer | self.driver).write({'phone': '+351 900 000 000'})
        self.assertIn('+351 900 000 000', str(contract.calendar_start_date_id.description))

    def test_reading_creates_no_odometer(self):
        """Bug: computing meters_pickup_value creates a fleet.vehicle.odometer record."""
        contract = self.make_contract()
        Odometer = self.env['fleet.vehicle.odometer']
        before = Odometer.search_count([])
        contract.invalidate_recordset()
        contract.meters_pickup_value  # noqa: B018 - reading is the action under test
        self.assertEqual(Odometer.search_count([]), before)

    def test_set_pickup_km_records_odometer(self):
        """Bug: setting the pick-up km records nothing unless the field was read first.

        The inverse writes on odometer_pickup_id, which only the compute's side
        effect creates; on a fresh record the value is silently lost."""
        contract = self.make_contract()
        contract.meters_pickup_value = 1234
        odometers = self.env['fleet.vehicle.odometer'].search([('vehicle_id', '=', self.vehicle.id)])
        self.assertIn(1234, odometers.mapped('value'))
