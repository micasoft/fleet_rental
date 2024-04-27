# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
import logging

from datetime import datetime, date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class CarRentalContract(models.Model):
    _logger = logging.getLogger(__name__)
    
    _name = 'car.rental.contract'
    _inherit = 'mail.thread'
    _description = 'Fleet Rental Management'

    image = fields.Binary(related='vehicle_id.image_128',
                          string="Image of Vehicle")
    
    reserved_fleet_id = fields.Many2one('car.rental.reserved',
                                        invisible=True,
                                        copy=False)
    name = fields.Char(string="Name",
                       default="Quote Contract",
                       readonly=True,
                       copy=False)
    customer_id = fields.Many2one('res.partner',
                                  required=True,
                                  string='Customer',
                                  help="Customer")
    vehicle_id = fields.Many2one('fleet.vehicle',
                                 string="Vehicle",
                                 required=True,
                                 help="Vehicle")
    car_brand = fields.Many2one('fleet.vehicle.model.brand',
                                string="Fleet Brand",
                                size=50,
                                related='vehicle_id.model_id.brand_id',
                                store=True,
                                readonly=True)
    car_color = fields.Char(string="Fleet Color",
                            size=50,
                            related='vehicle_id.color',
                            store=True,
                            copy=False,
                            default='#FFFFFF',
                            readonly=True)
    rent_cost = fields.Float(string="Rent Cost",
                        help="This fields is to determine the cost of rent",
                        required=True)
    rent_by_hour = fields.Boolean(string="Rent By Hour",
                                  help="Enable to start contract on "
                                       "hour basis",
                                  default=True)
    rent_start_date = fields.Date(string="Rent Start Date",
                                  required=True,
                                  default=str(date.today()),
                                  help="Start date of contract",
                                  track_visibility='onchange')
    start_time = fields.Char(string="Start By",
                             help="Enter the contract starting hour")
    pickup_location = fields.Char(string="Pickup location",
                           help="Enter the pickup location",
                           required=True)
    rent_end_date = fields.Date(string="Rent End Date",
                                required=True,
                                help="End date of contract",
                                track_visibility='onchange')
    end_time = fields.Char(string="End By",
                           help="Enter the contract Ending hour")
    dropoff_location = fields.Char(string="Drop off location",
                           help="Enter the drop off location",
                           required=True)

    state = fields.Selection(
        [('draft', 'Quote'), ('reserved', 'Reserved'), ('running', 'Running'),
         ('cancel', 'Cancel'),
         ('checking', 'Checking'), ('invoice', 'Invoice'), ('done', 'Done')],
        string="State", default="draft",
        copy=False, track_visibility='onchange')

    notes = fields.Text(string="Details & Notes")
    
    cost_generated = fields.Float(string='Recurring Cost',
                                  help="Costs paid at regular intervals, depending on the cost frequency")
    
    cost_frequency = fields.Selection(
        [('no', 'No'), ('daily', 'Daily'), ('weekly', 'Weekly'),
         ('monthly', 'Monthly')], string="Recurring Cost Frequency",
        help='Frequency of the recurring cost', default="no", required=True)
    
    journal_type = fields.Many2one('account.journal', 'Journal',
                                   default=lambda self: self.env[
                                       'account.journal'].search(
                                       [('id', '=', 1)]))
    account_type = fields.Many2one('account.account', 'Account',
                                   default=lambda self: self.env[
                                       'account.account'].search(
                                       [('id', '=', 17)]))
    recurring_line = fields.One2many('car.rental.line', 'rental_number',
                                     readonly=True, help="Recurring Invoices",
                                     copy=False)
    first_payment = fields.Float(string='First Payment',
                                 help="Transaction/Office/Contract charge "
                                      "amount, must paid by customer side "
                                      "other "
                                      "than recurrent payments",
                                 track_visibility='onchange',
                                 required=True)
    first_payment_inv = fields.Many2one('account.move', copy=False)
    first_invoice_created = fields.Boolean(string="First Invoice Created",
                                           invisible=True, copy=False)
    attachment_ids = fields.Many2many('ir.attachment',
                                      'car_rental_checklist_ir_attachments_rel',
                                      'rental_id', 'attachment_id',
                                      string="Attachments",
                                      help="Images of the vehicle before "
                                           "contract/any attachments")
    line_tools = fields.One2many('car.rental.line.tools',
                                     'checklist_number', string="Checklist",
                                     help="Facilities/Accessories, That should"
                                          " verify when closing the contract.")
    tools_cost = fields.Float(string="Total (Accessories/Tools)", readonly=True,
                         copy=False)
    
    damage_cost = fields.Float(string="Damage Cost / Balance Amount",
                               copy=False)
    
    total_cost = fields.Float(string="Total", readonly=True, copy=False)
    
    invoice_count = fields.Integer(compute='_invoice_count',
                                   string='# Invoice', copy=False)

    sales_person = fields.Many2one('res.users', string='Sales Person',
                                   default=lambda self: self.env.uid,
                                   track_visibility='always')
    read_only = fields.Boolean(string="Read Only", help="To make field read "
                                                        "only")
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company,
                                 help="Company this record owns")

    def action_run(self):
        """
            Set the state of the object to 'running'.
        """
        self.state = 'running'

    @api.constrains('rent_start_date', 'rent_end_date')
    def validate_dates(self):
        """
            Check the validity of the 'rent_start_date' and 'rent_end_date'
            fields.
            Raise a warning if 'rent_end_date' is earlier than
            'rent_start_date'.
        """
        if self.rent_end_date < self.rent_start_date:
            raise UserError("Please select the valid end date.")

    def set_to_done(self):
        """
            Set the state of the object to 'done' based on certain conditions related to invoices.
            Raise a UserError if certain invoices are pending or the total cost is zero.
        """
        #Double check if requires payment verification
        #self._verify_payment()
        self.state = 'done'

    def _check_availability(self):
        if self.rent_by_hour:
            _rent_from = datetime.combine(self.rent_start_date, datetime.strptime(self.start_time, "%H:%M").time())
            _rent_to = datetime.combine(self.rent_end_date, datetime.strptime(self.end_time, "%H:%M").time())
        else:
            _rent_from = datetime.combine(self.rent_start_date, datetime.strptime("00:00", "%H:%M").time())
            _rent_to = datetime.combine(self.rent_end_date, datetime.strptime("23:59", "%H:%M").time())
        
        check_availability = True
        for each in self.vehicle_id.rental_reserved_time:
            if each.date_from <= _rent_to and each.date_to >= _rent_from:
                check_availability = False
        return check_availability, _rent_from, _rent_to 
    
    def _verify_payment(self):
        invoice_ids = self.env['account.move'].search(
            [('fleet_rent_id', '=', self.id)])
        if any(each.payment_state != 'paid' for each in
               invoice_ids):
            raise UserError("Some Invoices are pending")

    def _invoice_count(self):
        """
            Calculate the count of invoices related to the current object.
            Update the 'invoice_count' field accordingly.
        """
        self.invoice_count = self.env['account.move'].search_count(
            [('fleet_rent_id', '=', self.id)])

    @api.constrains('state')
    def state_changer(self):
        """
            Handle state transitions and update the 'state_id' of the
            associated vehicle based on the value of the 'state' field.
        """
        if self.state == "running":
            state_id = self.env.ref('fleet_rental.vehicle_state_rent').id
            self.vehicle_id.write({'state_id': state_id})
        elif self.state in ("cancel", "invoice"):
            state_id = self.env.ref('fleet_rental.vehicle_state_active').id
            self.vehicle_id.write({'state_id': state_id})

    @api.constrains('line_tools', 'damage_cost', 'first_payment', 'rent_cost')
    def total_updater(self):
        """
           Update various fields related to totals based on the values in
           'line_tools', 'damage_cost', 'first_payment', 'cost' and other relevant fields.
       """
        tools_cost = 0.0
        for records in self.line_tools:
            tools_cost += records.price
        self.tools_cost = tools_cost
        self.total_cost = self.first_payment + self.rent_cost + self.tools_cost + self.damage_cost

    def fleet_scheduler1(self, rent_date):
        """
            Perform actions related to fleet scheduling, including creating
            invoices, managing recurring data, and sending email notifications.
        """
        inv_obj = self.env['account.move']
        recurring_obj = self.env['car.rental.line']
        supplier = self.customer_id

        self.env['ir.config_parameter'].sudo().get_param(
                'fleet_rental_send_booking')
        

        product = self.env['product.product'].search(
            [('id', '=', self.env['ir.config_parameter'].sudo().get_param('fleet_service_product_id'))], 
            limit=1)
        if product.property_account_income_id.id:
            income_account = product.property_account_income_id
        elif product.categ_id.property_account_income_categ_id.id:
            income_account = product.categ_id.property_account_income_categ_id
        else:
            raise UserError(
                _('Please define income account for this product: "%s" (id:%d).') % (
                    product.name,
                    product.id))
        inv_data = {
            'ref': supplier.name,
            'partner_id': supplier.id,
            'journal_id': self.journal_type.id,
            'invoice_origin': self.name,
            'fleet_rent_id': self.id,
            'invoice_payment_term_id': None,
            'invoice_date_due': self.rent_end_date,
            'move_type': 'out_invoice',
            'invoice_line_ids': [(0, 0, {
                'account_id': income_account.id,
                'price_unit': self.cost_generated,
                'quantity': 1,
                'product_id': product.id,
            })]
        }
        inv_id = inv_obj.create(inv_data)

        recurring_data = {
            'name': self.vehicle_id.name,
            'date_today': rent_date,
            'account_info': income_account.name,
            'rental_number': self.id,
            'recurring_amount': self.cost_generated,
            'invoice_number': inv_id.id,
            'invoice_ref': inv_id.id,
        }
        recurring_obj.create(recurring_data)

        if self.env['ir.config_parameter'].sudo().get_param('fleet_rental_send_recurring_reminder'):
            reservation_template = self.env.ref('fleet_rental.mail_template_recurring_reminder')
            reservation_template.send_mail(self.id) 

    @api.model
    def fleet_scheduler(self):
        """
            Perform fleet scheduling operations, including creating invoices,
            managing recurring data, and sending email notifications.
        """
        inv_obj = self.env['account.move']
        recurring_obj = self.env['car.rental.line']
        today = date.today()
        for records in self.search([]):
            start_date = datetime.strptime(str(records.rent_start_date),
                                           '%Y-%m-%d').date()
            end_date = datetime.strptime(str(records.rent_end_date),
                                         '%Y-%m-%d').date()
            if end_date >= date.today():
                temp = 0
                if records.cost_frequency == 'daily':
                    temp = 1
                elif records.cost_frequency == 'weekly':
                    week_days = (date.today() - start_date).days
                    if week_days % 7 == 0 and week_days != 0:
                        temp = 1
                elif records.cost_frequency == 'monthly':
                    if start_date.day == date.today().day and start_date != date.today():
                        temp = 1
                elif records.cost_frequency == 'yearly':
                    if start_date.day == date.today().day and start_date.month == date.today().month and \
                            start_date != date.today():
                        temp = 1
                if temp == 1 and records.cost_frequency != "no" and records.state == "running":
                    supplier = records.customer_id
                    product = self.env['product.product'].search(
                        [('id', '=', self.env['ir.config_parameter'].sudo().get_param('fleet_service_product_id'))], 
                        limit=1)
                    if product.property_account_income_id.id:
                        income_account = product.property_account_income_id
                    elif product.categ_id.property_account_income_categ_id.id:
                        income_account = product.categ_id.property_account_income_categ_id
                    else:
                        raise UserError(
                            _('Please define income account for this product: "%s" (id:%d).') % (
                                product.name,
                                product.id))
                    inv_data = {
                        'ref': supplier.name,
                        'partner_id': supplier.id,
                        'currency_id': records.account_type.company_id.currency_id.id,
                        'journal_id': records.journal_type.id,
                        'invoice_origin': records.name,
                        'fleet_rent_id': records.id,
                        'invoice_date': today,
                        'company_id': records.account_type.company_id.id,
                        'invoice_payment_term_id': None,
                        'invoice_date_due': records.rent_end_date,
                        'move_type': 'out_invoice',
                        'invoice_line_ids': [(0, 0, {
                            'account_id': income_account.id,
                            'price_unit': records.cost_generated,
                            'quantity': 1,
                            'product_id': product.id,
                        })]
                    }
                    inv_id = inv_obj.create(inv_data)
                    recurring_data = {
                        'name': records.vehicle_id.name,
                        'date_today': today,
                        'account_info': income_account.name,
                        'rental_number': records.id,
                        'recurring_amount': records.cost_generated,
                        'invoice_number': inv_id.id,
                        'invoice_ref': inv_id.id,
                    }
                    recurring_obj.create(recurring_data)

                    mail_content = _(
                        '<h3>Reminder Recurrent Payment!</h3><br/>Hi %s, <br/> This is to remind you that the '
                        'recurrent payment for the '
                        'rental contract has to be done.'
                        'Please make the payment at the earliest.'
                        '<br/><br/>'
                        'Please find the details below:<br/><br/>'
                        '<table><tr><td>Contract Ref<td/><td> %s<td/><tr/>'
                        '<tr/><tr><td>Amount <td/><td> %s<td/><tr/>'
                        '<tr/><tr><td>Due Date <td/><td> %s<td/><tr/>'
                        '<tr/><tr><td>Responsible Person <td/><td> %s, %s<td/><tr/><table/>') % \
                                   (self.customer_id.name, self.name,
                                    inv_id.amount_total,
                                    inv_id.invoice_date_due,
                                    inv_id.user_id.name,
                                    inv_id.user_id.mobile)
                    main_content = {
                        'subject': "Reminder Recurrent Payment!",
                        'author_id': self.env.user.partner_id.id,
                        'body_html': mail_content,
                        'email_to': self.customer_id.email,
                    }
                    self.env['mail.mail'].create(main_content).send()
            else:
                if self.state == 'running':
                    records.state = "checking"

    def action_verify(self):
        """
            Verifies the damage cost or missing cost
        """
        self.state = "invoice"
        self.reserved_fleet_id.unlink()
        #self.rent_end_date = fields.Date.today()
        product = self.env['product.product'].search(
            [('id', '=', self.env['ir.config_parameter'].sudo().get_param('fleet_service_product_id'))], 
            limit=1)
        if product.property_account_income_id.id:
            income_account = product.property_account_income_id
        elif product.categ_id.property_account_income_categ_id.id:
            income_account = product.categ_id.property_account_income_categ_id
        else:
            raise UserError(
                _('Please define income account for this product: "%s" (id:%d).') % (
                    product.name,
                    product.id))
 
        if self.total_cost != 0:
            inv_lines = []

            if self.rent_cost > 0:
                inv_lines.append((0, 0, {
                        'name': self.vehicle_id.name,
                        'account_id': income_account.id,
                        'price_unit': self.rent_cost,
                        'quantity': 1,
                        'product_id': product.id,
                    }))
        
            if self.tools_cost > 0:
                inv_lines.append((0, 0, {
                        'name': "Accessories/Tools",
                        'account_id': income_account.id,
                        'price_unit': self.tools_cost,
                        'quantity': 1,
                        'product_id': product.id,
                    }))

            if self.damage_cost > 0:
                inv_lines.append((0, 0, {
                        'name': "Damage/Tools missing cost",
                        'account_id': income_account.id,
                        'price_unit': self.damage_cost,
                        'quantity': 1,
                        'product_id': product.id,
                    }))
            
            supplier = self.customer_id
            inv_data = {
                'ref': supplier.name,
                'move_type': 'out_invoice',
                'partner_id': supplier.id,
                'currency_id': self.account_type.company_id.currency_id.id,
                'journal_id': self.journal_type.id,
                'invoice_origin': self.name,
                'fleet_rent_id': self.id,
                'company_id': self.account_type.company_id.id,
                'invoice_date_due': self.rent_end_date,
                'invoice_line_ids': inv_lines
            }

            inv_id = self.env['account.move'].create(inv_data)
        
            action = self.env.ref('account.action_move_out_invoice_type')
            result = {
                'name': action.name,
                'type': 'ir.actions.act_window',
                'views': [[False, 'form']],
                'target': 'current',
                'res_id': inv_id.id,
                'res_model': 'account.move',
            }
            return result
    
    def action_send_quote(self):
        check_availability, _, _ = self._check_availability()
        if not check_availability:
           raise UserError(
                'Sorry This vehicle is already booked by another customer')

        quote_template = self.env.ref('fleet_rental.mail_template_quote')
        quote_template.send_mail(self.id, force_send=True)

    def action_confirm(self):
        """
           Confirm the rental contract, check vehicle availability, update
           state to "reserved," generate a sequence code, and send a
           confirmation email.
        """
        check_availability, _rent_from, _rent_to = self._check_availability()
        if check_availability:
            reserved_id = self.vehicle_id.rental_reserved_time.create(
                {'customer_id': self.customer_id.id,
                 'date_from': _rent_from,
                 'date_to': _rent_to,
                 'reserved_obj_id': self.vehicle_id.id
                 })
            self.write({'reserved_fleet_id': reserved_id.id})
        else:
            raise UserError(
                'Sorry This vehicle is already booked by another customer')
        self.state = "reserved"
        sequence_code = 'car.rental.sequence'
        order_date = self.create_date
        order_date = str(order_date)[0:10]
        self.name = self.env['ir.sequence'] \
            .with_context(ir_sequence_date=order_date).next_by_code(
            sequence_code)
        
        if self.env['ir.config_parameter'].sudo().get_param('fleet_rental_send_booking'):
            reservation_template = self.env.ref('fleet_rental.mail_template_reserved')
            reservation_template.send_mail(self.id, force_send=True)

    def action_cancel(self):
        """
           Cancel the rental contract.
           Update the state to "cancel" and delete the associated reserved
           fleet ID if it exists.
       """
        self.state = "cancel"
#        self.vehicle_id.rental_check_availability = True
        if self.reserved_fleet_id:
            self.reserved_fleet_id.unlink()

    def force_checking(self):
        """
            Force the checking of payment status for associated invoices.
            If all invoices are marked as paid, update the state to "checking."
            Otherwise, raise a UserError indicating that some invoices are
            pending.
        """

        #Double check if requires payment verification
        #self._verify_payment()
        self.state = "checking"

    def action_view_invoice(self):
        """
            Display the associated invoices for the current record.
            Construct the appropriate view configurations based on the number
            of invoices found.
        """
        inv_obj = self.env['account.move'].search(
            [('fleet_rent_id', '=', self.id)])
        inv_ids = []
        for each in inv_obj:
            inv_ids.append(each.id)
        view_id = self.env.ref('account.view_move_form').id
        if inv_ids:
            if len(inv_ids) <= 1:
                value = {
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'account.move',
                    'view_id': view_id,
                    'type': 'ir.actions.act_window',
                    'name': _('Invoice'),
                    'res_id': inv_ids and inv_ids[0]
                }
            else:
                value = {
                    'domain': [('fleet_rent_id', '=', self.id)],
                    'view_type': 'form',
                    'view_mode': 'tree,form',
                    'res_model': 'account.move',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': _('Invoice'),
                }
            return value

    def action_invoice_create(self):
        """
            Create an invoice for the rental contract.
            Calculate the rental duration and iterate over each day to create
            invoices.
            Create the first payment invoice, add relevant invoice line data,
            and send an email notification for the received payment.
        """
        for each in self:
            rent_date = self.rent_start_date
            if each.cost_frequency != 'no' and rent_date < date.today():
                rental_days = (date.today() - rent_date).days
                if each.cost_frequency == 'weekly':
                    rental_days = int(rental_days / 7)
                if each.cost_frequency == 'monthly':
                    rental_days = int(rental_days / 30)
                if each.cost_frequency == 'yearly':
                    rental_days = int(rental_days / 365)
                for _ in range(0, rental_days + 1):
                    if rent_date > datetime.strptime(str(each.rent_end_date),
                                                     "%Y-%m-%d").date():
                        break
                    each.fleet_scheduler1(rent_date)
                    if each.cost_frequency == 'daily':
                        rent_date = rent_date + timedelta(days=1)
                    if each.cost_frequency == 'weekly':
                        rent_date = rent_date + timedelta(days=7)
                    if each.cost_frequency == 'monthly':
                        rent_date = rent_date + timedelta(days=30)
                    if each.cost_frequency == 'yearly':
                        rent_date = rent_date + timedelta(days=365)
        self.first_invoice_created = True
        inv_obj = self.env['account.move']
        supplier = self.customer_id
        inv_data = {
            'ref': supplier.name,
            'move_type': 'out_invoice',
            'partner_id': supplier.id,
            'currency_id': self.account_type.company_id.currency_id.id,
            'journal_id': self.journal_type.id,
            'invoice_origin': self.name,
            'fleet_rent_id': self.id,
            'company_id': self.account_type.company_id.id,
            'invoice_date_due': self.rent_end_date,
            'is_first_invoice': True,
        }
        inv_id = inv_obj.create(inv_data)
        self.first_payment_inv = inv_id.id

        product = self.env['product.product'].search(
            [('id', '=', self.env['ir.config_parameter'].sudo().get_param('fleet_service_product_id'))], 
            limit=1)

        if product.property_account_income_id.id:
            income_account = product.property_account_income_id.id
        elif product.categ_id.property_account_income_categ_id.id:
            income_account = product.categ_id.property_account_income_categ_id.id
        else:
            raise UserError(
                _('Please define income account for this product: "%s" (id:%d).') % (
                    product.name,
                    product.id))

        if inv_id:
            list_value = [(0, 0, {
                'name': self.vehicle_id.name,
                'price_unit': self.first_payment,
                'quantity': 1.0,
                'account_id': income_account,
                'product_id': product.id,
                'move_id': inv_id.id,
            })]
            inv_id.write({'invoice_line_ids': list_value})
        action = self.env.ref('account.action_move_out_invoice_type')
        result = {
            'name': action.name,
            'type': 'ir.actions.act_window',
            'views': [[False, 'form']],
            'target': 'current',
            'res_id': inv_id.id,
            'res_model': 'account.move',
        }
        return result

    def action_extend_rent(self):
        """
            Set the 'read_only' attribute to True, indicating that the rent
            extension action is being performed and the corresponding fields
            should be made read-only.

            This method is typically used in the context of extending a rental
            agreement.
        """
        self.read_only = True

    def action_confirm_extend_rent(self):
        """
            Confirm the extension of a rental agreement and update the rental
            reserved time for the associated vehicle.

            This method sets the 'date_to' field of the rental reserved time
            for the vehicle to the specified 'rent_end_date', indicating the
            extended rental period. After confirming the extension, the
            'read_only' attribute is set to False to allow further
            modifications.

            This method is typically called when a user confirms the extension
            of a rental.
        """
        self.reserved_fleet_id.write(
            {
                'date_to': self.rent_end_date,
            })
        self.read_only = False

    @api.constrains('start_time', 'end_time', 'rent_start_date',
                    'rent_end_date')
    def validate_time(self):
        """
            Validate the time constraints for a rental agreement.

            This method is used as a constraint to ensure that the specified
            start and end times are valid, especially when renting by the hour.
            If renting by the hour, it checks whether the end time is greater
            than the start time when the rental start and end
            dates are the same.

            :raises ValidationError: If the time constraints are not met, a
                                    validation error is raised with a relevant
                                    error message.
        """
        if self.rent_by_hour:
            start_time = datetime.strptime(self.start_time, "%H:%M").time()
            end_time = datetime.strptime(self.end_time, "%H:%M").time()
            if (self.rent_end_date == self.rent_start_date and
                    end_time <= start_time):
                raise ValidationError("Please choose a different end time")

    @api.constrains('rent_end_date')
    def validate_on_read_only(self):
        if self.read_only:
            old_date = self.reserved_fleet_id.date_to
            if self.rent_end_date <= old_date:
                raise ValidationError(
                    f"Please choose a date greater that {old_date}")

    def action_discard_extend(self):
        """
            Validate the 'rent_end_date' when the rental agreement is in
            read-only mode.

            This constraint checks if the rental agreement is marked as
            read-only, indicating that it has been extended or modified. If in
            read-only mode, it compares the 'rent_end_date' with the existing
            'date_to' value in the rental reserved time of the associated
            vehicle. It ensures that the 'rent_end_date' is greater than the
            existing date to maintain consistency.

            :raises ValidationError: If the 'rent_end_date' is not greater than
                                    the existing 'date_to', a validation error
                                    is raised with a relevant error message.
        """
        self.read_only = False
        self.rent_end_date = self.reserved_fleet_id.date_to
