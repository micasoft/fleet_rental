from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestSmoke(FleetRentalCommon):

    def test_module_installed(self):
        module = self.env['ir.module.module'].search([('name', '=', 'fleet_rental')])
        self.assertEqual(module.state, 'installed')

    def test_fixture_contract(self):
        contract = self.make_contract()
        self.assertEqual(contract.state, 'draft')
        self.assertEqual(contract.name, 'Quote Contract')

