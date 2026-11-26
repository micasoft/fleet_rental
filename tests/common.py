from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import new_test_user

TZ = 'Europe/Lisbon'


class FleetRentalCommon(AccountTestInvoicingCommon):
    """Shared fixtures: a company with a chart of accounts, a rentable
    vehicle with cost ranges, partners, tools and one user per group."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.ref('base.user_root').tz = TZ
        cls.env.user.tz = TZ
        # the fixture-building user manages rentals
        cls.env.user.groups_id = [Command.link(cls.env.ref('fleet_rental.fleet_car_rental_group_manager').id)]

        Partner = cls.env['res.partner']
        cls.customer = Partner.create({
            'name': 'Customer', 'email': 'customer@example.com',
            'phone': '+351 111 111 111'})
        cls.driver = Partner.create({'name': 'Driver', 'email': 'driver@example.com'})
        cls.owner = Partner.create({'name': 'Owner Lda', 'is_company': True})

        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'TestBrand'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'TestModel', 'brand_id': brand.id})
        cls.vehicle = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'owner': cls.owner.id, 'license_plate': 'AA-00-01',
            'company_id': cls.company.id,
            'rental_cost': [
                Command.create({'day_from': 1, 'day_to': 3, 'cost_per_day': 50}),
                Command.create({'day_from': 4, 'day_to': 10, 'cost_per_day': 40}),
            ],
        })
        cls.vehicle2 = cls.env['fleet.vehicle'].create({
            'model_id': model.id, 'owner': cls.owner.id, 'license_plate': 'AA-00-02',
            'company_id': cls.company.id})

        Tools = cls.env['car.rental.tools']
        cls.tool_once = Tools.create({'name': 'Child seat', 'unit': 'once', 'price': 10})
        cls.tool_daily = Tools.create({'name': 'GPS', 'unit': 'daily', 'price': 5})

        cls.service_product = cls.env['product.product'].create({
            'name': 'Rental service', 'type': 'service', 'taxes_id': [Command.clear()],
            'property_account_income_id': cls.company_data['default_account_revenue'].id,
        })
        cls.sales_journal = cls.company_data['default_journal_sale']

        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('fleet_rental_tolerance_delay', '3')
        params.set_param('fleet_rental_service_product_id', str(cls.service_product.product_tmpl_id.id))
        for key in ('fleet_rental_calendar_sync', 'fleet_rental_send_booking',
                    'fleet_rental_send_recurring_reminder'):
            params.set_param(key, False)

        def user(login, groups):
            return new_test_user(cls.env, login=login, groups=groups, tz=TZ,
                                 company_id=cls.company.id, company_ids=[Command.set(cls.company.ids)])
        cls.user_limited = user('rental_limited', 'base.group_user,fleet_rental.fleet_car_rental_group_limited')
        cls.user_normal = user('rental_normal', 'fleet_rental.fleet_car_rental_group_user')
        cls.user_manager = user('rental_manager', 'fleet_rental.fleet_car_rental_group_manager')

    @classmethod
    def share_sequence(cls):
        """Make the contract sequence usable by the test company.

        Works around the multi-company sequence bug (pinned by
        TestReservation.test_confirm_assigns_number) so other tests get
        contract numbers."""
        cls.env['ir.sequence'].sudo().search(
            [('code', '=', 'car.rental.sequence')]).company_id = False

    def make_contract(self, **vals):
        values = {
            'customer_id': self.customer.id,
            'driver_id': self.driver.id,
            'vehicle_id': self.vehicle.id,
            'pickup_location': 'Porto',
            'dropoff_location': 'Lisboa',
            'rent_start_date': '2026-03-02 10:00:00',
            'rent_end_date': '2026-03-05 10:00:00',
            'rent_cost': 150,
            'first_payment': 50,
            'cost_frequency': 'no',
            'journal_type': self.sales_journal.id,
        }
        values.update(vals)
        return self.env['car.rental.contract'].create(values)

    def confirm(self, contract):
        contract.action_confirm()
        return contract
