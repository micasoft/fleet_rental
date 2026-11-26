from odoo import Command
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestReport(FleetRentalCommon):

    def test_report_reads_all_fields(self):
        """Bug: the report's SQL view uses wrong column names (cost, tools_cost)."""
        contract = self.make_contract(damage_cost=30)
        contract.line_tools = [Command.create({'name': self.tool_once.id, 'quantity': 1, 'price': 25})]
        self.env.flush_all()
        row = self.env['report.fleet.rental'].sudo().search_read(
            [('id', '=', contract.id)], ['rent_cost', 'total', 'damage_cost', 'total_cost'])[0]
        self.assertEqual(
            (row['rent_cost'], row['total'], row['damage_cost'], row['total_cost']),
            (150, 25, 30, contract.total_cost))

    def test_report_states_match_contract(self):
        """Bug: the report's state list lacks 'reserved' and 'invoice'."""
        def keys(model):
            return {key for key, _label in self.env[model]._fields['state'].selection}
        self.assertEqual(keys('report.fleet.rental'), keys('car.rental.contract'))

    def test_every_model_has_access_rules(self):
        """Bug: report.fleet.rental has no access rules (only superuser can read it)."""
        names = self.env['ir.model.data'].search(
            [('module', '=', 'fleet_rental'), ('model', '=', 'ir.model')]).mapped('res_id')
        missing = [
            model.model for model in self.env['ir.model'].browse(names)
            if not model.transient and not self.env[model.model]._abstract
            and not self.env['ir.model.access'].search_count([('model_id', '=', model.id)])
        ]
        self.assertEqual(missing, [])
