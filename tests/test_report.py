from odoo import Command
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestReport(FleetRentalCommon):

    def test_report_reads_all_fields(self):
        """The analysis report shows rent, tools, damage and total."""
        contract = self.make_contract(damage_cost=30)
        contract.line_tools = [Command.create({'name': self.tool_once.id, 'quantity': 1, 'price': 25})]
        self.env.flush_all()
        row = self.env['report.fleet.rental'].sudo().search_read(
            [('id', '=', contract.id)], ['rent_cost', 'total', 'damage_cost', 'total_cost'])[0]
        self.assertEqual(
            (row['rent_cost'], row['total'], row['damage_cost'], row['total_cost']),
            (150, 25, 30, contract.total_cost))

    def test_report_states_match_contract(self):
        """The report offers every contract state."""
        def keys(model):
            return {key for key, _label in self.env[model]._fields['state'].selection}
        self.assertEqual(keys('report.fleet.rental'), keys('car.rental.contract'))

    def test_every_model_has_access_rules(self):
        """Every model of the module has access rules."""
        names = self.env['ir.model.data'].search(
            [('module', '=', 'fleet_rental'), ('model', '=', 'ir.model')]).mapped('res_id')
        missing = [
            model.model for model in self.env['ir.model'].browse(names)
            if not model.transient and not self.env[model.model]._abstract
            and not self.env['ir.model.access'].search_count([('model_id', '=', model.id)])
        ]
        self.assertEqual(missing, [])

    # -- printed documents and e-mails ------------------------------------------

    def test_pdfs_use_company_layout(self):
        """Both PDFs carry the company header (web.external_layout)."""
        contract = self.confirm(self.make_contract())
        self.company.name = 'Rent-a-Test Lda'
        for report in ('fleet_rental.car_rental_contract_pdf', 'fleet_rental.car_rental_reserve_pdf'):
            with self.subTest(report=report):
                html, _type = self.env['ir.actions.report']._render_qweb_html(report, contract.ids)
                self.assertIn('Rent-a-Test Lda', html.decode())
                self.assertIn(contract.name, html.decode())

    def test_mail_templates_render(self):
        """Every template renders, with the company logo instead of a placeholder."""
        contract = self.confirm(self.make_contract())
        invoice = self.init_invoice('out_invoice', amounts=[100])
        for xmlid in ('mail_template_quote', 'mail_template_reserved',
                      'mail_template_recurring_reminder', 'mail_template_next_pickup',
                      'mail_template_next_dropoff'):
            with self.subTest(template=xmlid):
                template = self.env.ref(f'fleet_rental.{xmlid}').with_context(invoice=invoice)
                body = str(template._render_field('body_html', contract.ids)[contract.id])
                self.assertIn(self.customer.name if xmlid in (
                    'mail_template_quote', 'mail_template_reserved',
                    'mail_template_recurring_reminder') else contract.name, body)
                self.assertNotIn('placehold.co', body)
