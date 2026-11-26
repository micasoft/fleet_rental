from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.addons.mail.tests.common import MockEmail
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('post_install', '-at_install', 'fleet_rental')
class TestInvoicing(FleetRentalCommon, MockEmail):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.share_sequence()

    # -- helpers ------------------------------------------------------------

    def cron_model(self):
        return self.env['car.rental.contract'].with_user(self.env.ref('base.user_root'))

    def running(self, **vals):
        contract = self.confirm(self.make_contract(**vals))
        contract.action_run()
        return contract

    def invoices(self, contract):
        return self.env['account.move'].search([('fleet_rent_id', '=', contract.id)])

    def recurring_dates(self, contract):
        recurring = self.invoices(contract).filtered(lambda m: not m.is_first_invoice)
        return sorted(recurring.mapped('invoice_date'))

    def issue_recurring(self, contract, amount, invoice_date):
        """An already issued recurring invoice, as the recurring path records it."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': contract.customer_id.id,
            'fleet_rent_id': contract.id, 'invoice_date': invoice_date,
            'journal_id': self.sales_journal.id,
            'invoice_line_ids': [Command.create({
                'name': contract.vehicle_id.name, 'price_unit': amount, 'quantity': 1,
                'product_id': self.service_product.id, 'tax_ids': [Command.clear()]})],
        })
        self.env['car.rental.line'].create({
            'name': contract.vehicle_id.name, 'date_today': invoice_date,
            'rental_number': contract.id, 'recurring_amount': amount,
            'invoice_number': move.id, 'invoice_ref': move.id})
        return move

    def add_tool(self, contract, tool, quantity, price):
        contract.line_tools = [Command.create({'name': tool.id, 'quantity': quantity, 'price': price})]

    def verify(self, contract):
        contract.state = 'checking'
        action = contract.action_verify()
        return self.env['account.move'].browse(action['res_id']) if action else self.env['account.move']

    def payment_mails(self):
        return self._new_mails.filtered(lambda m: (m.subject or '').startswith('Payment Received'))

    # -- service product ------------------------------------------------------

    def test_service_product_ids_align(self):
        """Precondition for the other tests: in a fresh database the fixture
        product's template and variant ids are equal, so the template-vs-variant
        bug below does not mask other results."""
        self.assertEqual(self.service_product.id, self.service_product.product_tmpl_id.id)

    def test_no_income_account_raises(self):
        """Bug: `for _ in range(...)` in action_invoice_create shadows the translation
        function, so this message crashes with UnboundLocalError instead of showing."""
        self.service_product.property_account_income_id = False
        self.service_product.categ_id.property_account_income_categ_id = False
        contract = self.running()
        with self.assertRaisesRegex(UserError, self.service_product.name):
            contract.action_invoice_create()

    def test_service_product_param_missing_falls_back(self):
        """Bug: without fleet_rental_service_product_id (fresh install) invoicing fails.

        The setting is only stored once Settings are saved; the module's own
        service product must be used meanwhile."""
        self.env['ir.config_parameter'].sudo().search(
            [('key', '=', 'fleet_rental_service_product_id')]).unlink()
        contract = self.running()
        contract.action_invoice_create()
        self.assertEqual(contract.first_payment_inv.invoice_line_ids.product_id,
                         self.env.ref('fleet_rental.fleet_service_product'))

    def test_service_product_param_is_template(self):
        """Bug: the setting stores a product.template id, the code searches product.product by it."""
        attribute = self.env['product.attribute'].create({
            'name': 'Size', 'value_ids': [Command.create({'name': 'S'}), Command.create({'name': 'L'})]})
        self.env['product.template'].create({
            'name': 'Two variants', 'attribute_line_ids': [Command.create({
                'attribute_id': attribute.id, 'value_ids': [Command.set(attribute.value_ids.ids)]})]})
        template = self.env['product.template'].create({
            'name': 'Other rental service', 'type': 'service', 'taxes_id': [Command.clear()],
            'property_account_income_id': self.company_data['default_account_revenue'].id})
        self.assertNotEqual(template.id, template.product_variant_id.id)
        self.env['ir.config_parameter'].sudo().set_param('fleet_rental_service_product_id', str(template.id))
        contract = self.running()
        contract.action_invoice_create()
        self.assertEqual(contract.first_payment_inv.invoice_line_ids.product_id.product_tmpl_id, template)

    # -- first invoice --------------------------------------------------------

    def test_first_invoice(self):
        contract = self.running()
        contract.action_invoice_create()
        invoice = self.invoices(contract)
        self.assertEqual(len(invoice), 1)
        self.assertTrue(invoice.is_first_invoice)
        self.assertEqual(invoice.move_type, 'out_invoice')
        self.assertEqual(invoice.partner_id, self.customer)
        self.assertEqual(invoice.invoice_line_ids.mapped('price_unit'), [50])
        self.assertEqual(contract.first_payment_inv, invoice)
        self.assertTrue(contract.first_invoice_created)

    # -- recurring invoices ---------------------------------------------------

    def test_recurring_daily(self):
        """Bug: action_invoice_create crashes for recurring frequencies (datetime vs date)."""
        contract = self.running(cost_frequency='daily', cost_generated=100)
        with freeze_time('2026-03-05 12:00:00'):
            contract.action_invoice_create()
        self.assertEqual(self.recurring_dates(contract),
                         [date(2026, 3, d) for d in (2, 3, 4, 5)])
        recurring = self.invoices(contract).filtered(lambda m: not m.is_first_invoice)
        self.assertEqual(set(recurring.mapped('amount_untaxed')), {100})
        self.assertEqual(set(recurring.invoice_line_ids.mapped('name')), {self.vehicle.name})
        self.assertEqual(recurring.partner_id, self.customer)
        self.assertEqual(len(contract.recurring_line), 4)

    def test_recurring_weekly(self):
        """Bug: action_invoice_create crashes for recurring frequencies (datetime vs date)."""
        contract = self.running(cost_frequency='weekly', cost_generated=100,
                                rent_end_date='2026-03-20 10:00:00')
        with freeze_time('2026-03-20 12:00:00'):
            contract.action_invoice_create()
        self.assertEqual(self.recurring_dates(contract),
                         [date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16)])

    def test_recurring_monthly_end_of_month(self):
        """Bug: action_invoice_create crashes for recurring frequencies; months are 30 days.

        Monthly = same day of each calendar month, last day of shorter months."""
        contract = self.running(cost_frequency='monthly', cost_generated=100,
                                rent_start_date='2026-01-31 10:00:00',
                                rent_end_date='2026-04-15 10:00:00')
        with freeze_time('2026-04-15 12:00:00'):
            contract.action_invoice_create()
        self.assertEqual(self.recurring_dates(contract),
                         [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)])

    def test_recurring_cron_bills_contract(self):
        """Bug: the cron's recurring path uses the empty model instead of the contract.

        Also: the cron runs in the cron user's company, so company-dependent
        values (income account) come from the wrong company ("Incompatible
        companies"). A missed day is caught up on the next run."""
        contract = self.running(cost_frequency='daily', cost_generated=100)
        with freeze_time('2026-03-03 12:00:00'):
            self.cron_model().fleet_scheduler()
        self.assertEqual(self.recurring_dates(contract), [date(2026, 3, 2), date(2026, 3, 3)])
        recurring = self.invoices(contract).filtered(lambda m: not m.is_first_invoice)
        self.assertEqual(set(recurring.invoice_line_ids.mapped('name')), {self.vehicle.name})

    def test_recurring_idempotent(self):
        """Bug: running the recurring billing again the same day creates duplicates."""
        contract = self.running(cost_frequency='daily', cost_generated=100)
        with freeze_time('2026-03-03 12:00:00'):
            contract.action_invoice_create()
            self.cron_model().fleet_scheduler()
            self.cron_model().fleet_scheduler()
        self.assertEqual(self.recurring_dates(contract), [date(2026, 3, 2), date(2026, 3, 3)])

    def test_recurring_reminder_mail(self):
        """Bug: the recurring reminder is sent for the empty model (send_mail(self.id))."""
        self.env['ir.config_parameter'].sudo().set_param('fleet_rental_send_recurring_reminder', True)
        contract = self.running(cost_frequency='daily', cost_generated=100)
        with freeze_time('2026-03-02 12:00:00'), self.mock_mail_gateway():
            self.cron_model().fleet_scheduler()
        mails = self._new_mails.filtered(
            lambda m: m.model == 'car.rental.contract' and m.res_id == contract.id)
        self.assertEqual(len(mails), 1)

    # -- final invoice ----------------------------------------------------------

    def test_final_invoice_lines(self):
        contract = self.running()
        self.add_tool(contract, self.tool_once, 1, 10)
        self.add_tool(contract, self.tool_daily, 3, 5)
        contract.damage_cost = 30
        invoice = self.verify(contract)
        self.assertEqual(sorted(invoice.invoice_line_ids.mapped('price_unit')), [25, 30, 100])
        self.assertEqual(contract.state, 'invoice')
        self.assertFalse(self.vehicle.rental_reserved_time)

    def test_final_invoice_omits_zero_lines(self):
        contract = self.running()
        invoice = self.verify(contract)
        self.assertEqual(invoice.invoice_line_ids.mapped('price_unit'), [100])

    def test_final_invoice_subtracts_recurring(self):
        """Bug: the final invoice ignores recurring invoices already issued (billed twice).

        300 rent - 50 first payment - 2 x 100 recurring + 20 tools + 30 damage = 100."""
        contract = self.running(rent_cost=300, cost_frequency='weekly', cost_generated=100)
        self.issue_recurring(contract, 100, date(2026, 3, 2))
        self.issue_recurring(contract, 100, date(2026, 3, 9))
        self.add_tool(contract, self.tool_once, 1, 20)
        contract.damage_cost = 30
        invoice = self.verify(contract)
        self.assertEqual(invoice.amount_untaxed, 100)

    def test_default_journal_is_sales(self):
        """Bug: the default journal is the journal with id 1, of any type and company."""
        company2 = self.setup_other_company()['company']
        Contract = self.env['car.rental.contract'].with_company(company2)
        journal = self.env['account.journal'].browse(Contract.default_get(['journal_type']).get('journal_type'))
        self.assertEqual(journal.type, 'sale')
        self.assertEqual(journal.company_id, company2)

    def test_invoice_count_and_view(self):
        contract = self.running()
        self.issue_recurring(contract, 100, date(2026, 3, 2))
        self.issue_recurring(contract, 100, date(2026, 3, 3))
        self.assertEqual(contract.invoice_count, 2)
        action = contract.action_view_invoice()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertIn(('fleet_rent_id', '=', contract.id), action['domain'])

    # -- cancelling invoices --------------------------------------------------

    def test_cancel_first_invoice_resets_flag(self):
        contract = self.running()
        contract.action_invoice_create()
        contract.first_payment_inv.button_cancel()
        self.assertFalse(contract.first_invoice_created)

    def test_cancel_final_invoice_back_to_checking(self):
        contract = self.running()
        invoice = self.verify(contract)
        invoice.button_cancel()
        self.assertEqual(contract.state, 'checking')

    def test_cancel_recurring_invoice_keeps_state(self):
        """Bug: cancelling any rental invoice moves a non-running contract to checking."""
        contract = self.running(cost_frequency='daily', cost_generated=100)
        recurring = self.issue_recurring(contract, 100, date(2026, 3, 2))
        self.verify(contract)
        recurring.button_cancel()
        self.assertEqual(contract.state, 'invoice')

    def test_cancel_invoice_of_done_contract(self):
        """Bug: cancelling an invoice of a done contract moves it back to checking."""
        contract = self.running()
        contract.action_invoice_create()
        contract.state = 'done'
        contract.first_payment_inv.button_cancel()
        self.assertEqual(contract.state, 'done')

    def test_cancel_two_invoices(self):
        """Bug: button_cancel assumes one invoice (fails on several contracts)."""
        c1 = self.running()
        c2 = self.running(vehicle_id=self.vehicle2.id)
        inv1 = self.issue_recurring(c1, 100, date(2026, 3, 2))
        inv2 = self.issue_recurring(c2, 100, date(2026, 3, 2))
        (inv1 | inv2).button_cancel()
        self.assertEqual(set((inv1 | inv2).mapped('state')), {'cancel'})

    def test_cancel_invoice_without_contract(self):
        invoice = self.init_invoice('out_invoice', partner=self.customer, amounts=[100])
        invoice.button_cancel()
        self.assertEqual(invoice.state, 'cancel')

    # -- first payment mail ---------------------------------------------------

    def pay_first_invoice(self, **wizard_vals):
        contract = self.running()
        contract.action_invoice_create()
        invoice = contract.first_payment_inv
        invoice.action_post()
        with self.mock_mail_gateway():
            self.env['account.payment.register'].with_context(
                active_model='account.move', active_ids=invoice.ids,
            ).create(wizard_vals).action_create_payments()
        return invoice

    def test_first_payment_mail_default_memo(self):
        self.pay_first_invoice()
        mails = self.payment_mails()
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.email_to, self.customer.email)

    def test_first_payment_mail_custom_memo(self):
        """Bug: the paid invoice is looked up by name = payment memo; a custom memo sends nothing."""
        self.pay_first_invoice(communication='XYZ')
        self.assertEqual(len(self.payment_mails()), 1)
