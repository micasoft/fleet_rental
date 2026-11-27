import base64
from datetime import timedelta

from odoo import fields
from odoo.tests import Form, tagged

from .common import FleetRentalCommon

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n')
PICKUP_SEARCH = 'fleet_rental.car_rental_contract_pickup_search'
DROPOFF_SEARCH = 'fleet_rental.car_rental_contract_dropoff_search'


@tagged('post_install', '-at_install', 'fleet_rental')
class TestViews(FleetRentalCommon):
    """Every screen loads for the people who use it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        me = cls.user_limited.partner_id
        cls.contract = cls.make_contract(cls, handle_pickup=me.id, handle_dropoff=me.id)
        cls.contract.action_confirm()

    def action_views(self, xmlid, user):
        action = self.env.ref(xmlid)
        views = [(view.view_id.id, view.view_mode) for view in action.view_ids] \
            or [(False, mode) for mode in action.view_mode.split(',')]
        views.append((action.search_view_id.id, 'search'))
        result = self.env[action.res_model].with_user(user).get_views(
            views, {'load_filters': True, 'action_id': action.id})
        return action, result

    # -- pickup / drop-off (phone) ------------------------------------------------

    def test_staff_actions_load_for_limited_user(self):
        for xmlid in ('fleet_rental.action_car_rental_contract_pickup',
                      'fleet_rental.action_car_rental_contract_dropoff'):
            with self.subTest(action=xmlid):
                action, result = self.action_views(xmlid, self.user_limited)
                self.assertEqual(action.view_mode.split(',')[0], 'kanban')
                self.assertIn('kanban', result['views'])
                self.assertIn('search', result['views'])

    def test_pickup_form_as_limited_user(self):
        with Form(self.contract.with_user(self.user_limited),
                  view='fleet_rental.car_rental_contract_pickup_form') as form:
            form.meters_pickup_value = 12000
            form.signature_pickup = PNG
        self.assertEqual(self.contract.meters_pickup_value, 12000)

    def test_dropoff_form_as_limited_user(self):
        self.contract.action_run()
        with Form(self.contract.with_user(self.user_limited),
                  view='fleet_rental.car_rental_contract_dropoff_form') as form:
            form.meters_dropoff_value = 12500
        self.assertEqual(self.contract.meters_dropoff_value, 12500)

    def test_staff_today_filters(self):
        now = fields.Datetime.now().replace(hour=12, minute=0, second=0)
        today = self.make_contract(vehicle_id=self.vehicle2.id, rent_start_date=now,
                                   rent_end_date=now + timedelta(days=3))
        tomorrow = self.make_contract(vehicle_id=self.vehicle2.id,
                                      rent_start_date=now + timedelta(days=4, hours=-12),
                                      rent_end_date=now + timedelta(days=6))
        Contract = self.env['car.rental.contract']
        pickups = Contract.search(self.filter_domain(PICKUP_SEARCH, 'pickup_today'))
        self.assertIn(today, pickups)
        self.assertNotIn(tomorrow, pickups)
        returns = Contract.search(self.filter_domain(DROPOFF_SEARCH, 'dropoff_today'))
        self.assertNotIn(today, returns)

    # -- back office (desktop) ---------------------------------------------------

    def test_contract_action_views_load(self):
        action, result = self.action_views('fleet_rental.action_car_rental_contract', self.user_normal)
        for view_type in ('list', 'kanban', 'calendar', 'form', 'search'):
            self.assertIn(view_type, result['views'])

    def test_contract_form_opens(self):
        with Form(self.contract.with_user(self.user_normal),
                  view='fleet_rental.car_rental_contract_form') as form:
            form.notes = 'Customer asked for a baby seat'
        self.assertEqual(self.contract.notes, 'Customer asked for a baby seat')

    def test_contract_form_creates(self):
        with Form(self.env['car.rental.contract'].with_user(self.user_normal),
                  view='fleet_rental.car_rental_contract_form') as form:
            form.customer_id = self.customer
            form.driver_id = self.driver
            form.vehicle_id = self.vehicle2
            form.rent_start_date = fields.Datetime.to_datetime('2026-05-02 10:00:00')
            form.rent_end_date = fields.Datetime.to_datetime('2026-05-04 10:00:00')
            form.pickup_location = 'Porto'
            form.dropoff_location = 'Porto'
        self.assertEqual(form.record.rent_cost, 120)

    def test_contract_search_filters(self):
        search = 'fleet_rental.car_rental_contract_search'
        draft = self.make_contract(vehicle_id=self.vehicle2.id)
        Contract = self.env['car.rental.contract']
        self.assertIn(draft, Contract.search(self.filter_domain(search, 'filter_quote')))
        reserved = Contract.search(self.filter_domain(search, 'filter_reserved'))
        self.assertIn(self.contract, reserved)
        self.assertNotIn(draft, reserved)
        self.contract.action_run()
        self.assertIn(self.contract, Contract.search(self.filter_domain(search, 'filter_running')))
        self.contract.force_checking()
        self.assertIn(self.contract, Contract.search(self.filter_domain(search, 'filter_to_check')))
        mine = Contract.with_user(self.user_normal).search(
            self.filter_domain(search, 'filter_mine', self.user_normal))
        self.assertNotIn(self.contract, mine)
