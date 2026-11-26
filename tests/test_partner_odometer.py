from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestPartnerOdometer(FleetRentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_write_two_partners(self):
        """Saving several contacts at once works and re-syncs their contracts' events."""
        self.env['ir.config_parameter'].sudo().set_param('fleet_rental_calendar_sync', True)
        contract = self.confirm(self.make_contract())
        (self.customer | self.driver).write({'phone': '+351 900 000 000'})
        self.assertIn('+351 900 000 000', str(contract.calendar_start_date_id.description))

    def test_reading_creates_no_odometer(self):
        """Reading a contract creates no odometer record."""
        contract = self.make_contract()
        Odometer = self.env['fleet.vehicle.odometer']
        before = Odometer.search_count([])
        contract.invalidate_recordset()
        contract.meters_pickup_value  # noqa: B018 - reading is the action under test
        self.assertEqual(Odometer.search_count([]), before)

    def test_set_pickup_km_records_odometer(self):
        """Setting the pick-up km records an odometer value, even on a contract never read before."""
        contract = self.make_contract()
        contract.meters_pickup_value = 1234
        odometers = self.env['fleet.vehicle.odometer'].search([('vehicle_id', '=', self.vehicle.id)])
        self.assertIn(1234, odometers.mapped('value'))
