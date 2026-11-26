from datetime import datetime

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestPricing(FleetRentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Vehicle = cls.env['fleet.vehicle']
        common = {'model_id': cls.model.id, 'owner': cls.owner.id, 'company_id': cls.company.id}
        # bands 1-3 and 4-10 only: nothing covers 11+ days
        cls.priced = Vehicle.create(dict(common, license_plate='AA-00-03', rental_cost=[
            Command.create({'day_from': 1, 'day_to': 3, 'cost_per_day': 50}),
            Command.create({'day_from': 4, 'day_to': 10, 'cost_per_day': 40}),
        ]))
        cls.unpriced = Vehicle.create(dict(common, license_plate='AA-00-04'))

    def contract_form(self, start, end, vehicle=None):
        form = Form(self.env['car.rental.contract'], view='fleet_rental.car_rental_contract_form')
        form.customer_id = self.customer
        form.driver_id = self.driver
        form.vehicle_id = vehicle or self.vehicle
        form.pickup_location = 'Porto'
        form.dropoff_location = 'Lisboa'
        form.rent_start_date = datetime.fromisoformat(start)
        form.rent_end_date = datetime.fromisoformat(end)
        return form

    # -- duration ---------------------------------------------------------

    def test_days_same_day(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-02 18:00')
        self.assertEqual(form.contract_days, 1)

    def test_days_next_day_within_tolerance(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-03 12:00')
        self.assertEqual(form.contract_days, 1)

    def test_days_next_day_over_tolerance(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-03 14:00')
        self.assertEqual(form.contract_days, 2)

    def test_days_zero(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-02 10:00')
        self.assertEqual(form.contract_days, 0)

    def test_end_before_start_raises(self):
        form = self.contract_form('2026-03-05 10:00', '2026-03-06 10:00')
        with self.assertRaises(UserError):
            form.rent_end_date = datetime(2026, 3, 4, 10, 0)

    def test_days_without_tolerance_param(self):
        """Without the setting (fresh install, Settings never saved) the
        tolerance is the default 3 hours, not 0."""
        self.restore_installed_param('fleet_rental_tolerance_delay')
        form = self.contract_form('2026-03-02 10:00', '2026-03-03 12:00')
        self.assertEqual(form.contract_days, 1)

    # -- price --------------------------------------------------------------

    def test_cost_per_day_from_range(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-05 10:00')
        self.assertEqual(form.contract_days, 3)
        self.assertEqual(form.car_cost_per_day, 50)
        self.assertEqual(form.rent_cost, 150)
        form.rent_end_date = datetime(2026, 3, 7, 10, 0)
        self.assertEqual(form.contract_days, 5)
        self.assertEqual(form.car_cost_per_day, 40)
        self.assertEqual(form.rent_cost, 200)

    def test_cost_per_day_no_range(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-05 10:00', vehicle=self.unpriced)
        self.assertEqual(form.car_cost_per_day, 0)
        self.assertEqual(form.rent_cost, 0)

    def test_tools_quantities_and_totals(self):
        form = self.contract_form('2026-03-02 10:00', '2026-03-05 10:00')
        for tool in (self.tool_once, self.tool_daily):
            with form.line_tools.new() as line:
                line.name = tool
        contract = form.save()
        contract.damage_cost = 7  # not editable in Quote; set as at check-in
        quantities = {line.name: line.quantity for line in contract.line_tools}
        self.assertEqual(quantities, {self.tool_once: 1, self.tool_daily: 3})
        self.assertEqual(contract.tools_cost, 25)
        self.assertEqual(contract.total_cost, 150 + 25 + 7)

    # -- cost ranges --------------------------------------------------------

    def add_range(self, day_from, day_to):
        self.priced.write({'rental_cost': [
            Command.create({'day_from': day_from, 'day_to': day_to, 'cost_per_day': 30})]})

    def test_range_overlap_rejected(self):
        with self.assertRaises(UserError):
            self.add_range(3, 5)

    def test_range_inverted_rejected(self):
        with self.assertRaises(UserError):
            self.add_range(12, 11)  # overlaps nothing: only the order is wrong

    def test_range_from_below_one_rejected(self):
        with self.assertRaises(UserError):
            self.add_range(-2, 0)

    def test_range_error_names_the_band(self):
        with self.assertRaisesRegex(UserError, '12.11'):
            self.add_range(12, 11)

    def test_range_single_day_allowed(self):
        self.add_range(11, 11)
        self.assertIn((11, 11), [(r.day_from, r.day_to) for r in self.priced.rental_cost])

    # -- a price band must cover the rental -------------------------------

    def priced_contract(self, vehicle, end):
        return self.make_contract(vehicle_id=vehicle.id, rent_start_date='2026-03-02 10:00:00',
                                  rent_end_date=end)

    def test_confirm_covered_length(self):
        contract = self.priced_contract(self.priced, '2026-03-12 10:00:00')  # 10 days
        contract.action_confirm()
        self.assertEqual(contract.state, 'reserved')

    def test_confirm_longer_than_last_band_refused(self):
        contract = self.priced_contract(self.priced, '2026-03-13 10:00:00')  # 11 days
        with self.assertRaisesRegex(UserError, '11 days'):
            contract.action_confirm()
        self.assertEqual(contract.state, 'draft')

    def test_confirm_in_gap_between_bands_refused(self):
        self.priced.rental_cost.filtered(lambda r: r.day_from == 4).day_from = 5  # gap: day 4
        contract = self.priced_contract(self.priced, '2026-03-06 10:00:00')  # 4 days
        with self.assertRaisesRegex(UserError, '4 days'):
            contract.action_confirm()

    def test_confirm_vehicle_without_bands_refused(self):
        contract = self.priced_contract(self.unpriced, '2026-03-05 10:00:00')
        with self.assertRaises(UserError):
            contract.action_confirm()
