from datetime import datetime

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestPricing(FleetRentalCommon):

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
        """Bug: missing fleet_rental_tolerance_delay counts 0 hours, not 3.

        The parameter only exists once Settings are saved; on a fresh install
        int(False) gives no tolerance at all instead of the default 3 hours.
        The test restores the install-time state, so shipping the default as
        data also fixes it."""
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
        form = self.contract_form('2026-03-02 10:00', '2026-03-05 10:00', vehicle=self.vehicle2)
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
        self.vehicle.write({'rental_cost': [
            Command.create({'day_from': day_from, 'day_to': day_to, 'cost_per_day': 30})]})

    def test_range_overlap_rejected(self):
        with self.assertRaises(UserError):
            self.add_range(3, 5)

    def test_range_inverted_rejected(self):
        with self.assertRaises(UserError):
            self.add_range(6, 5)

    def test_range_single_day_allowed(self):
        """Bug: a one-day range (day_from == day_to) is refused."""
        self.add_range(11, 11)
        self.assertIn((11, 11), [(r.day_from, r.day_to) for r in self.vehicle.rental_cost])
