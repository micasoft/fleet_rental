import base64
from datetime import datetime

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import FleetRentalCommon

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n')


@tagged('post_install', '-at_install', 'fleet_rental')
class TestSecurity(FleetRentalCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        me = cls.user_limited.partner_id
        other = cls.user_manager.partner_id
        Contract = cls.env['car.rental.contract']
        base = {
            'customer_id': cls.customer.id, 'driver_id': cls.driver.id,
            'pickup_location': 'Porto', 'dropoff_location': 'Lisboa',
            'rent_cost': 150, 'first_payment': 50, 'journal_type': cls.sales_journal.id,
        }
        cls.mine = Contract.create(dict(base, vehicle_id=cls.vehicle.id, handle_pickup=me.id,
                                        rent_start_date='2026-03-02 10:00:00',
                                        rent_end_date='2026-03-05 10:00:00'))
        cls.mine.action_confirm()
        cls.mine_draft = Contract.create(dict(base, vehicle_id=cls.vehicle.id, handle_pickup=me.id,
                                              rent_start_date='2026-04-02 10:00:00',
                                              rent_end_date='2026-04-05 10:00:00'))
        cls.others = Contract.create(dict(base, vehicle_id=cls.vehicle2.id,
                                          handle_pickup=other.id, handle_dropoff=other.id,
                                          rent_start_date='2026-03-02 10:00:00',
                                          rent_end_date='2026-03-05 10:00:00'))
        cls.others.action_confirm()
        cls.all_contracts = cls.mine | cls.mine_draft | cls.others

    @staticmethod
    def as_user(user, records):
        return records.with_user(user)

    # -- visibility -----------------------------------------------------------

    def test_limited_sees_own_reserved_running(self):
        visible = self.env['car.rental.contract'].with_user(self.user_limited).search([])
        self.assertEqual(visible, self.mine)

    def test_normal_sees_all(self):
        visible = self.env['car.rental.contract'].with_user(self.user_normal).search([])
        self.assertEqual(visible & self.all_contracts, self.all_contracts)

    def test_fleet_user_sees_all_vehicles(self):
        fleet_user = new_test_user(self.env, login='fleet_only', groups='base.group_user,fleet.fleet_group_user',
                                   company_id=self.company.id, company_ids=[Command.set(self.company.ids)])
        self.vehicle.driver_id = self.customer
        visible = self.env['fleet.vehicle'].with_user(fleet_user).search([])
        self.assertIn(self.vehicle, visible)

    # -- Pickup/Dropoff user rights -------------------------------------------

    def test_limited_can_write_pickup_fields(self):
        attachment = self.env['ir.attachment'].with_user(self.user_limited).create(
            {'name': 'photo.png', 'datas': PNG})
        values = {
            'rent_pickup_date': datetime(2026, 3, 2, 10, 15),
            'rent_dropoff_date': datetime(2026, 3, 5, 9, 45),
            'fuel_tunk_pickup': 0.5,
            'fuel_tunk_dropoff': 0.75,
            'meters_pickup_value': 12345,
            'attachment_pickup_ids': [Command.link(attachment.id)],
            'signature_pickup': PNG,
            'notes': 'Scratch on the left door',
        }
        for name, value in values.items():
            with self.subTest(field=name):
                self.as_user(self.user_limited, self.mine).write({name: value})

    def test_limited_cannot_write_other_fields(self):
        """Pickup/Dropoff users can change only the pick-up and drop-off fields."""
        for name, value in {'rent_cost': 1, 'customer_id': self.driver.id, 'state': 'done'}.items():
            with self.subTest(field=name), self.assertRaises(AccessError):
                self.as_user(self.user_limited, self.mine).write({name: value})

    def test_limited_cannot_run_actions(self):
        """Business actions are for rental users, not Pickup/Dropoff users."""
        for action in ('action_confirm', 'action_verify', 'action_cancel', 'action_invoice_create'):
            with self.subTest(action=action), self.assertRaises(AccessError):
                getattr(self.as_user(self.user_limited, self.mine), action)()

    # -- deletion -------------------------------------------------------------

    def soft_deleted(self, contracts):
        self.env.flush_all()
        self.env.cr.execute('SELECT id FROM car_rental_contract WHERE soft_deleted AND id IN %s',
                            [tuple(contracts.ids)])
        return {row[0] for row in self.env.cr.fetchall()}

    def test_manager_delete_is_soft(self):
        self.env['ir.config_parameter'].sudo().set_param('fleet_rental_calendar_sync', True)
        contracts = self.mine | self.others
        self.as_user(self.user_manager, contracts).unlink()
        self.assertEqual(self.soft_deleted(contracts), set(contracts.ids))
        self.assertFalse(self.env['car.rental.contract'].with_user(self.user_manager).search(
            [('id', 'in', contracts.ids)]))
        self.assertFalse(self.env['car.rental.reserved'].search(
            [('reserved_obj_id', 'in', (self.vehicle | self.vehicle2).ids)]))

    def test_normal_and_limited_cannot_delete(self):
        """Only users with delete rights (Administrator) may (soft-)delete a contract."""
        for user in (self.user_normal, self.user_limited):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.as_user(user, self.mine).unlink()

    # -- stored XSS -----------------------------------------------------------

    def test_tool_name_escaped(self):
        """Tool names are escaped in the Accessories/Tools list (no stored XSS)."""
        tool = self.env['car.rental.tools'].create({'name': '<img src=x onerror=alert(1)>', 'price': 1})
        self.mine.line_tools = [Command.create({'name': tool.id, 'price': 1})]
        html = str(self.mine.list_line_tools)
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)
