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
import base64
import hashlib
import json
import logging
from datetime import timedelta

import pytz
from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import SUPERUSER_ID, Command, api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import format_datetime

from .res_config_settings import DEFAULT_TOLERANCE_DELAY

_logger = logging.getLogger(__name__)

QUOTE_NAME = "Quote Contract"  # name of a contract until it gets its number
SEQUENCE_CODE = "car.rental.sequence"

STATES = [
    ('draft', 'Quote'),
    ('reserved', 'Reserved'),
    ('running', 'Running'),
    ('cancel', 'Cancel'),
    ('checking', 'Checking'),
    ('invoice', 'Invoice'),
    ('done', 'Done'),
]

COST_FREQUENCIES = [
    ('no', 'No'),
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
]

BILLING_STEP = {
    'daily': relativedelta(days=1),
    'weekly': relativedelta(weeks=1),
    'monthly': relativedelta(months=1),  # 31 Jan -> 28/29 Feb -> 31 Mar
}

GROUP_PICKUP = 'fleet_rental.fleet_car_rental_group_limited'
GROUP_USER = 'fleet_rental.fleet_car_rental_group_user'

# The only fields a Pickup/Dropoff user may change.
PICKUP_FIELDS = {
    'rent_pickup_date', 'rent_dropoff_date',
    'fuel_tunk_pickup', 'fuel_tunk_dropoff',
    'meters_pickup_value', 'odometer_pickup_id',
    'meters_dropoff_value', 'odometer_dropoff_id',
    'attachment_pickup_ids', 'attachment_dropoff_ids',
    'signature_pickup', 'signature_dropoff', 'send_contract',
    'notes',
}

# Changing any of these fields changes the totals, so the quote must be re-sent.
PRICE_FIELDS = {'rent_cost', 'line_tools', 'damage_cost'}

# Changing any of these fields may change the contract's calendar events.
CALENDAR_FIELDS = {
    'state', 'vehicle_id', 'customer_id', 'driver_id', 'sales_person',
    'handle_pickup', 'handle_dropoff', 'pickup_location', 'dropoff_location',
    'rent_start_date', 'rent_end_date', 'notes',
}


class CarRentalContract(models.Model):
    _name = 'car.rental.contract'
    _inherit = ['mail.thread']
    _description = 'Fleet Rental Contract'

    # -- fields --------------------------------------------------------------

    name = fields.Char(string="Name", default=QUOTE_NAME, readonly=True, copy=False)
    state = fields.Selection(STATES, string="State", default='draft', copy=False, tracking=True)
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company,
                                 help="Company this record owns")
    company_currency_id = fields.Many2one(related='company_id.currency_id')
    soft_deleted = fields.Boolean(default=False)
    notes = fields.Text(string="Details & Notes")

    # people
    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    driver_id = fields.Many2one('res.partner', string='Driver', required=True, tracking=True)
    driver_extra_id = fields.Many2one('res.partner', string='Extra Driver', tracking=True)
    sales_person = fields.Many2one('res.partner', string='Sales Person',
                                   default=lambda self: self.env.user.partner_id)
    handle_pickup = fields.Many2one('res.partner', string='Handle Pickup',
                                    help="Person in charge of the pick-up",
                                    default=lambda self: self.env.user.partner_id)
    handle_dropoff = fields.Many2one('res.partner', string='Handle Drop off',
                                     help="Person in charge of the drop-off",
                                     default=lambda self: self.env.user.partner_id)

    # vehicle
    vehicle_id = fields.Many2one('fleet.vehicle', string="Vehicle", required=True, tracking=True)
    image = fields.Binary(related='vehicle_id.image_128', string="Image of Vehicle")
    car_description = fields.Char(string="Car Description",
                                  related='vehicle_id.model_id.display_name')
    car_deposit = fields.Monetary(string="Car Deposit", related='vehicle_id.deposit', store=True,
                                  help='Security deposit/Insurance excess',
                                  currency_field='company_currency_id')
    car_km_included_per_day = fields.Integer(string="Km(s) included",
                                             related='vehicle_id.km_included_per_day',
                                             store=True, tracking=True)
    car_km_extra = fields.Monetary(string="Km(s) extra", related='vehicle_id.km_extra',
                                   store=True, tracking=True,
                                   currency_field='company_currency_id')
    reserved_fleet_id = fields.Many2one('car.rental.reserved', copy=False)

    # period
    rent_start_date = fields.Datetime(string="Rent Start Date", required=True,
                                      default=fields.Datetime.now,
                                      help="Start date of contract")
    rent_end_date = fields.Datetime(string="Rent End Date", required=True, tracking=True,
                                    help="End date of contract")
    rent_start_date_locale = fields.Char(compute='_compute_dates_locale',
                                         string="Rent Start Date (locale)")
    rent_end_date_locale = fields.Char(compute='_compute_dates_locale',
                                       string="Rent End Date (locale)")
    contract_days = fields.Integer(compute='_compute_contract_days',
                                   string='Number of Contract days')
    pickup_location = fields.Char(string="Pickup location", required=True)
    dropoff_location = fields.Char(string="Return location", required=True)
    read_only = fields.Boolean(string="Read Only",
                               help="Set while the rent is being extended")

    # prices
    car_cost_per_day = fields.Float(string="Cost per day", default=0, tracking=True)
    rent_cost = fields.Float(string="Rent Cost", required=True, tracking=True)
    line_tools = fields.One2many('car.rental.line.tools', 'contract_id', string="Checklist",
                                 help="Facilities/Accessories, That should"
                                      " verify when closing the contract.")
    list_line_tools = fields.Html(string="Accessories/Tools",
                                  compute='_compute_list_line_tools', sanitize=False)
    tools_cost = fields.Float(string="Total (Accessories/Tools)", copy=False,
                              compute='_compute_totals', store=True)
    damage_cost = fields.Float(string="Damage Cost / Balance Amount", copy=False)
    total_cost = fields.Float(string="Total", copy=False, compute='_compute_totals', store=True)
    sent_quote = fields.Boolean(string="Quote sent", default=False, copy=False)

    # invoicing
    journal_type = fields.Many2one('account.journal', 'Journal',
                                   default=lambda self: self._default_journal())
    first_payment = fields.Float(string='First Payment', required=True,
                                 help="Transaction/Office/Contract charge amount, paid by "
                                      "the customer on top of the recurring payments")
    first_payment_inv = fields.Many2one('account.move', copy=False)
    first_invoice_created = fields.Boolean(string="First Invoice Created", copy=False)
    cost_generated = fields.Float(string='Recurring Cost',
                                  help="Amount billed at each period of the cost frequency")
    cost_frequency = fields.Selection(COST_FREQUENCIES, string="Recurring Cost Frequency",
                                      help='Frequency of the recurring cost',
                                      default='no', required=True)
    recurring_line = fields.One2many('car.rental.line', 'rental_number', readonly=True,
                                     help="Recurring Invoices", copy=False)
    invoice_count = fields.Integer(compute='_compute_invoice_count', string='# Invoice')

    # attachments
    attachment_ids = fields.Many2many('ir.attachment',
                                      'car_rental_contract_ir_attachments_rel',
                                      'rental_id', 'attachment_id', string="Attachments",
                                      help="Images of the vehicle before contract/any attachments")

    # calendar
    calendar_start_date_id = fields.Many2one('calendar.event', copy=False)
    calendar_start_date_hash = fields.Char(string="Calendar start data hash", readonly=True)
    calendar_end_date_id = fields.Many2one('calendar.event', copy=False)
    calendar_end_date_hash = fields.Char(string="Calendar end data hash", readonly=True)

    # pick-up and drop-off (recorded by the staff on their phone)
    rent_pickup_date = fields.Datetime(string="Picked up at", required=True,
                                       default=fields.Datetime.now,
                                       help="Date and time when the car was picked up")
    fuel_tunk_pickup = fields.Float(string="Fuel at pickup", default=0.0)
    odometer_pickup_id = fields.Many2one('fleet.vehicle.odometer', string="Odometer at pickup",
                                         tracking=True)
    meters_pickup_value = fields.Float(string='Km at pickup',
                                       compute='_compute_meters_pickup_value',
                                       inverse='_inverse_meters_pickup_value')
    meters_pickup_unit = fields.Selection(string="Unit", related='odometer_pickup_id.unit')
    attachment_pickup_ids = fields.Many2many('ir.attachment',
                                             'car_rental_contract_pickup_ir_attachments_rel',
                                             'rental_id', 'attachment_id',
                                             string="Pickup photos",
                                             help="Pictures taken at the pickup")
    signature_pickup = fields.Binary("Customer signature (pickup)")
    send_contract = fields.Boolean(string="Send a contract to client", default=False)
    rent_dropoff_date = fields.Datetime(string="Dropped off at", required=True,
                                        default=fields.Datetime.now,
                                        help="Date and time when the car was dropped off")
    fuel_tunk_dropoff = fields.Float(string="Fuel at drop-off", default=0.0)
    odometer_dropoff_id = fields.Many2one('fleet.vehicle.odometer', string="Odometer at drop-off",
                                          tracking=True)
    meters_dropoff_value = fields.Float(string='Km at drop-off',
                                        compute='_compute_meters_dropoff_value',
                                        inverse='_inverse_meters_dropoff_value')
    meters_dropoff_unit = fields.Selection(string="Drop-off unit", related='odometer_dropoff_id.unit')
    attachment_dropoff_ids = fields.Many2many('ir.attachment',
                                              'car_rental_contract_dropoff_ir_attachments_rel',
                                              'rental_id', 'attachment_id',
                                              string="Drop-off photos",
                                              help="Pictures taken at the drop-off")
    signature_dropoff = fields.Binary("Customer signature (drop-off)")

    # -- defaults --------------------------------------------------------------

    @api.model
    def _default_journal(self):
        return self.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', self.env.company.id)], limit=1)

    # -- computes ---------------------------------------------------------------

    def _compute_dates_locale(self):
        for contract in self:
            contract.rent_start_date_locale = format_datetime(
                self.env, contract.rent_start_date, dt_format=False)
            contract.rent_end_date_locale = format_datetime(
                self.env, contract.rent_end_date, dt_format=False)

    @api.depends('rent_start_date', 'rent_end_date')
    def _compute_contract_days(self):
        """Days billed: a day starts every 24 hours, after a grace period
        (the tolerance delay) for late returns. An invalid period counts 0."""
        tolerance = timedelta(hours=self._tolerance_delay())
        for contract in self:
            start, end = contract.rent_start_date, contract.rent_end_date
            if start and end and end >= start:
                contract.contract_days = (end - start - tolerance).days + 1
            else:
                contract.contract_days = 0

    @api.depends('line_tools.price', 'line_tools.quantity', 'rent_cost', 'damage_cost')
    def _compute_totals(self):
        for contract in self:
            contract.tools_cost = sum(line.price * line.quantity for line in contract.line_tools)
            contract.total_cost = contract.rent_cost + contract.tools_cost + contract.damage_cost

    @api.depends('line_tools.name.name')
    def _compute_list_line_tools(self):
        for contract in self:
            items = Markup().join(Markup("<li>%s</li>") % line.name.name
                                  for line in contract.line_tools if line.name)
            contract.list_line_tools = Markup("<ul>%s</ul>") % items

    def _compute_invoice_count(self):
        for contract in self:
            contract.invoice_count = self.env['account.move'].search_count(
                [('fleet_rent_id', '=', contract.id)])

    @api.depends('odometer_pickup_id.value')
    def _compute_meters_pickup_value(self):
        for contract in self:
            contract.meters_pickup_value = contract.odometer_pickup_id.value

    def _inverse_meters_pickup_value(self):
        for contract in self:
            contract._write_odometer('odometer_pickup_id', contract.meters_pickup_value)

    @api.depends('odometer_dropoff_id.value')
    def _compute_meters_dropoff_value(self):
        for contract in self:
            contract.meters_dropoff_value = contract.odometer_dropoff_id.value

    def _inverse_meters_dropoff_value(self):
        for contract in self:
            contract._write_odometer('odometer_dropoff_id', contract.meters_dropoff_value)

    def _write_odometer(self, field, value):
        """Record a km reading on the contract's odometer entry `field`,
        creating the entry on the first reading."""
        self.ensure_one()
        odometer = self[field]
        if odometer:
            odometer.write({'value': value, 'date': fields.Date.context_today(self)})
        elif value:
            self[field] = self.env['fleet.vehicle.odometer'].create({
                'vehicle_id': self.vehicle_id.id,
                'value': value,
                'date': fields.Date.context_today(self),
            })

    # -- onchanges (form only) ---------------------------------------------------

    @api.onchange('rent_start_date', 'rent_end_date')
    def _onchange_rent_dates(self):
        self._check_dates()
        self._update_tool_quantities()

    @api.onchange('vehicle_id', 'rent_start_date', 'rent_end_date')
    def _onchange_price(self):
        self._apply_band_price()

    @api.onchange('line_tools')
    def _onchange_line_tools(self):
        self._update_tool_quantities()

    # -- constraints ---------------------------------------------------------------

    @api.constrains('rent_start_date', 'rent_end_date')
    def _check_dates(self):
        for contract in self:
            if contract.rent_start_date and contract.rent_end_date \
                    and contract.rent_end_date < contract.rent_start_date:
                raise ValidationError(_("Please select the valid end date."))

    @api.constrains('rent_end_date')
    def validate_on_read_only(self):
        """While extending, the new end date must be after the reserved one."""
        for contract in self.filtered('read_only'):
            old_end = contract.reserved_fleet_id.date_to
            if old_end and contract.rent_end_date <= old_end:
                raise ValidationError(_("Please choose a date later than %s", old_end))

    # -- ORM overrides --------------------------------------------------------------

    def write(self, vals):
        self._check_pickup_user_write(vals)
        if PRICE_FIELDS & set(vals) and 'sent_quote' not in vals:
            vals = dict(vals, sent_quote=False)
        result = super().write(vals)
        if 'state' in vals:
            self._update_vehicle_state()
        if CALENDAR_FIELDS & set(vals):
            self._sync_calendar()
        return result

    def unlink(self):
        """Soft delete: hide the contract, free the vehicle, drop the events."""
        self.check_access('unlink')
        self._release_vehicle()
        self.write({'soft_deleted': True})
        _logger.info("Contracts %s were soft deleted", self.ids)
        return True

    # -- rights ---------------------------------------------------------------------

    def _is_pickup_user(self):
        user = self.env.user
        return not self.env.su and user.has_group(GROUP_PICKUP) and not user.has_group(GROUP_USER)

    def _check_pickup_user_write(self, vals):
        forbidden = set(vals) - PICKUP_FIELDS
        if forbidden and self._is_pickup_user():
            raise AccessError(_(
                "Pickup/Dropoff users can only change the pick-up and drop-off details "
                "(not allowed: %s).", ", ".join(sorted(forbidden))))

    def _check_manage_rights(self):
        """Business actions are for rental users, not Pickup/Dropoff users."""
        if self._is_pickup_user():
            raise AccessError(_("Only rental users can do this."))

    # -- settings ----------------------------------------------------------------------

    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    def _tolerance_delay(self):
        """Hours a customer may return late before another day is charged."""
        return int(self._get_param('fleet_rental_tolerance_delay', DEFAULT_TOLERANCE_DELAY) or 0)

    def _service_product(self):
        """The product used on rental invoices.

        The setting stores a product template; without it (fresh install)
        the module's own service product is used."""
        template_id = self._get_param('fleet_rental_service_product_id')
        template = self.env['product.template'].browse(int(template_id or 0)).exists()
        return template.product_variant_id or self.env.ref('fleet_rental.fleet_service_product')

    # -- local time ----------------------------------------------------------------------

    def _local_tz(self):
        tz = (self.env.context.get('tz') or self.env.user.tz
              or self.env.company.partner_id.tz or 'UTC')
        return pytz.timezone(tz)

    def _local_date(self, value):
        """The local date of a UTC datetime."""
        return pytz.utc.localize(value).astimezone(self._local_tz()).date()

    def _local_today(self):
        return self._local_date(fields.Datetime.now())

    # -- pricing --------------------------------------------------------------------------

    def _price_band(self):
        """The vehicle's price band covering the contract length, if any."""
        self.ensure_one()
        days = self.contract_days
        return self.vehicle_id.rental_cost.filtered(
            lambda band: band.day_from <= days <= band.day_to)[:1]

    def _apply_band_price(self):
        """Daily price from the price band, rent = daily price x days."""
        for contract in self:
            contract.car_cost_per_day = contract._price_band().cost_per_day
            contract.rent_cost = contract.car_cost_per_day * max(contract.contract_days, 0)

    def _check_price_band(self):
        """Refuse a contract whose length no price band of its vehicle covers
        (it would be rented for free)."""
        for contract in self:
            if not contract._price_band():
                raise UserError(_(
                    "No price band covers %(days)s days for vehicle %(vehicle)s. "
                    "Add one to the vehicle's rental prices.",
                    days=contract.contract_days, vehicle=contract.vehicle_id.display_name))

    def _update_tool_quantities(self):
        for contract in self:
            for line in contract.line_tools:
                line.quantity = contract.contract_days if line.unit == 'daily' else 1

    # -- availability -----------------------------------------------------------------------

    def _check_availability(self):
        """Refuse a period that shares a day with another reservation of the
        vehicle. Prices are per day, so the return day is not free for another
        pick-up, whatever the hour."""
        day = self._local_date
        for contract in self:
            start, end = day(contract.rent_start_date), day(contract.rent_end_date)
            others = contract.vehicle_id.rental_reserved_time - contract.reserved_fleet_id
            if any(day(other.date_from) <= end and day(other.date_to) >= start
                   for other in others):
                raise UserError(_("Sorry, this vehicle is already booked by another customer."))

    def _release_vehicle(self):
        """Remove the reservation and the calendar events."""
        self.reserved_fleet_id.unlink()
        (self.calendar_start_date_id | self.calendar_end_date_id).unlink()

    # -- state actions ---------------------------------------------------------------------------

    def action_send_quote(self):
        self._check_manage_rights()
        self._check_availability()
        template = self.env.ref('fleet_rental.mail_template_quote')
        for contract in self:
            contract.sent_quote = True
            template.send_mail(contract.id, force_send=True)

    def action_confirm(self):
        """Reserve the vehicle, number the contract and send the booking mail."""
        self._check_manage_rights()
        self._check_price_band()
        self._check_availability()
        send_booking = self._get_param('fleet_rental_send_booking')
        for contract in self:
            contract.reserved_fleet_id = self.env['car.rental.reserved'].create({
                'customer_id': contract.customer_id.id,
                'date_from': contract.rent_start_date,
                'date_to': contract.rent_end_date,
                'reserved_obj_id': contract.vehicle_id.id,
            })
            values = {'state': 'reserved'}
            if contract.name in (False, QUOTE_NAME):  # keep the number on re-confirm
                values['name'] = contract._next_number()
            contract.write(values)
            if send_booking:
                self.env.ref('fleet_rental.mail_template_reserved').send_mail(
                    contract.id, force_send=True)

    def _next_number(self):
        self.ensure_one()
        return self._company_sequence(self.company_id).with_context(
            ir_sequence_date=fields.Date.to_string(self.create_date)
        ).next_by_id()

    @api.model
    def _company_sequence(self, company):
        """The company's contract sequence: each company numbers on its own.
        One is created, like the module's, the first time a company needs it."""
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([('code', '=', SEQUENCE_CODE),
                                    ('company_id', '=', company.id)], limit=1)
        if not sequence:
            template = self.env.ref('fleet_rental.sequence_car_rental', raise_if_not_found=False)
            sequence = Sequence.create({
                'name': template.name if template else "Car Rental Sequence",
                'code': SEQUENCE_CODE,
                'prefix': template.prefix if template else "RENT/%(range_year)s/",
                'padding': template.padding if template else 4,
                'use_date_range': template.use_date_range if template else True,
                'company_id': company.id,
            })
        return sequence

    def action_move_to_quote(self):
        self._check_manage_rights()
        self.reserved_fleet_id.unlink()
        self.state = 'draft'

    def action_run(self):
        self._check_manage_rights()
        self.state = 'running'

    def action_complete_pickup(self):
        """The staff hand the car over: the rental starts."""
        return self._complete_handover(
            'reserved', 'running', _("Pickup completed by %s"),
            lambda c: [
                _("the km at pickup") if c.meters_pickup_value <= 0 else None,
                _("the customer signature") if not c.signature_pickup else None,
            ])

    def action_complete_dropoff(self):
        """The car is back: the contract waits for the back office's check."""
        return self._complete_handover(
            'running', 'checking', _("Drop-off completed by %s"),
            lambda c: [
                _("the km at drop-off (at least %s)", c.meters_pickup_value)
                if c.meters_dropoff_value <= 0 or c.meters_dropoff_value < c.meters_pickup_value
                else None,
            ])

    def _complete_handover(self, from_state, to_state, message, missing):
        """Move contracts from `from_state` to `to_state` once nothing is
        `missing`. Pickup/Dropoff users may do it on the contracts they can
        write; the state itself is not a pickup field, hence the sudo."""
        self.check_access('write')
        for contract in self:
            if contract.state != from_state:
                raise UserError(_("%(contract)s is not %(state)s.", contract=contract.name,
                                  state=dict(STATES)[from_state]))
            todo = [item for item in missing(contract) if item]
            if todo:
                raise UserError(_("Please fill in %s first.", ", ".join(todo)))
            contract.sudo().write({'state': to_state})
            contract.sudo().message_post(body=message % self.env.user.name,
                                         author_id=self.env.user.partner_id.id)
        return True

    def force_checking(self):
        self._check_manage_rights()
        self.state = 'checking'

    def set_to_done(self):
        self._check_manage_rights()
        self.state = 'done'

    def action_cancel(self):
        self._check_manage_rights()
        self._release_vehicle()
        self.state = 'cancel'

    def _update_vehicle_state(self):
        rent = self.env.ref('fleet_rental.vehicle_state_rent')
        active = self.env.ref('fleet_rental.vehicle_state_active')
        for contract in self:
            if contract.state == 'running':
                contract.vehicle_id.state_id = rent
            elif contract.state in ('cancel', 'invoice'):
                contract.vehicle_id.state_id = active

    # -- extension -----------------------------------------------------------------------------

    def action_extend_rent(self):
        """Unlock the end date to extend the rent."""
        self._check_manage_rights()
        self.read_only = True

    def action_confirm_extend_rent(self):
        """Extend the reservation to the new end date and re-price the rent."""
        self._check_manage_rights()
        self._check_price_band()
        self._check_availability()
        for contract in self:
            contract.reserved_fleet_id.date_to = contract.rent_end_date
            contract._apply_band_price()
            contract._update_tool_quantities()
            contract.read_only = False

    def action_discard_extend(self):
        self._check_manage_rights()
        for contract in self:
            contract.write({'read_only': False, 'rent_end_date': contract.reserved_fleet_id.date_to})

    # -- crons ------------------------------------------------------------------------------------

    def _active_contracts(self, states):
        return self.search([('state', 'in', states), ('soft_deleted', '=', False)])

    @api.model
    def fleet_scheduler(self):
        """Daily: start the rentals of today, bill the recurring periods,
        move finished rentals to checking and close invoiced ones."""
        today = self._local_today()
        for contract in self._active_contracts(['reserved', 'running', 'invoice']):
            contract = contract.with_company(contract.company_id)
            if contract.state == 'reserved' and self._local_date(contract.rent_start_date) <= today:
                _logger.info("Contract %s moved to running", contract.id)
                contract.state = 'running'
            if contract.state == 'running':
                contract._bill_recurring_periods(today)
                if self._local_date(contract.rent_end_date) < today:
                    _logger.info("Contract %s moved to checking", contract.id)
                    contract.state = 'checking'
            elif contract.state == 'invoice':
                _logger.info("Contract %s moved to done", contract.id)
                contract.state = 'done'

    @api.model
    def next_event(self):
        """Daily: remind the handlers of tomorrow's pick-ups and drop-offs."""
        tomorrow = self._local_today() + timedelta(days=1)
        pickup = self.env.ref('fleet_rental.mail_template_next_pickup')
        for contract in self._active_contracts(['reserved']):
            if self._local_date(contract.rent_start_date) == tomorrow:
                pickup.send_mail(contract.id)
        dropoff = self.env.ref('fleet_rental.mail_template_next_dropoff')
        for contract in self._active_contracts(['running']):
            if self._local_date(contract.rent_end_date) == tomorrow:
                dropoff.send_mail(contract.id)

    # -- invoicing ----------------------------------------------------------------------------------

    def _income_account(self, product):
        product = product.with_company(self.company_id)
        account = (product.property_account_income_id
                   or product.categ_id.property_account_income_categ_id)
        if not account:
            raise UserError(_('Please define income account for this product: "%(name)s" (id:%(id)d).',
                              name=product.name, id=product.id))
        return account

    def _invoice_line(self, name, amount):
        product = self._service_product()
        return Command.create({
            'name': name,
            'product_id': product.id,
            'account_id': self._income_account(product).id,
            'price_unit': amount,
            'quantity': 1,
        })

    def _create_invoice(self, lines, **values):
        self.ensure_one()
        return self.env['account.move'].with_company(self.company_id).create({
            'move_type': 'out_invoice',
            'ref': self.customer_id.name,
            'partner_id': self.customer_id.id,
            'currency_id': self.company_id.currency_id.id,
            'journal_id': self.journal_type.id,
            'invoice_origin': self.name,
            'fleet_rent_id': self.id,
            'company_id': self.company_id.id,
            'invoice_date_due': self._local_date(self.rent_end_date),
            'invoice_line_ids': lines,
            **values,
        })

    def _invoice_action(self, invoice):
        return {
            'name': _('Invoice'),
            'type': 'ir.actions.act_window',
            'views': [[False, 'form']],
            'target': 'current',
            'res_id': invoice.id,
            'res_model': 'account.move',
        }

    def _billing_dates(self, until):
        """Start dates of the recurring periods up to `until`: the first on
        the start date, none after the end date."""
        self.ensure_one()
        step = BILLING_STEP.get(self.cost_frequency)
        if not step:
            return []
        start = self._local_date(self.rent_start_date)
        last = min(until, self._local_date(self.rent_end_date))
        dates, n = [], 0
        while start + step * n <= last:
            dates.append(start + step * n)
            n += 1
        return dates

    def _bill_recurring_periods(self, until):
        """Invoice every recurring period up to `until` not invoiced yet
        (catches up missed days, never bills a period twice)."""
        for contract in self:
            billed = set(contract.recurring_line.mapped('date_today'))
            for day in contract._billing_dates(until):
                if day not in billed:
                    contract._create_recurring_invoice(day)

    def _create_recurring_invoice(self, invoice_date):
        self.ensure_one()
        line = self._invoice_line(self.vehicle_id.name, self.cost_generated)
        invoice = self._create_invoice([line], invoice_date=invoice_date)
        self.env['car.rental.line'].create({
            'name': self.vehicle_id.name,
            'date_today': invoice_date,
            'account_info': invoice.invoice_line_ids.account_id.name,
            'rental_number': self.id,
            'recurring_amount': self.cost_generated,
            'invoice_number': invoice.id,
            'invoice_ref': invoice.id,
        })
        if self._get_param('fleet_rental_send_recurring_reminder'):
            self.env.ref('fleet_rental.mail_template_recurring_reminder').with_context(
                invoice=invoice).send_mail(self.id)
        return invoice

    def action_invoice_create(self):
        """Bill the recurring periods due so far, then the first payment."""
        self._check_manage_rights()
        invoice = self.env['account.move']
        for contract in self:
            contract._bill_recurring_periods(self._local_today())
            invoice = contract._create_invoice(
                [contract._invoice_line(contract.vehicle_id.name, contract.first_payment)],
                is_first_invoice=True)
            contract.write({'first_payment_inv': invoice.id, 'first_invoice_created': True})
        return self._invoice_action(invoice)

    def _recurring_invoiced(self):
        """Amount of the recurring invoices issued and not cancelled."""
        self.ensure_one()
        return sum(line.recurring_amount for line in self.recurring_line
                   if line.invoice_ref.state != 'cancel')

    def action_verify(self):
        """Close the rent (checking -> invoice) and issue the final invoice:
        rent - first payment - recurring invoices + tools + damage."""
        self._check_manage_rights()
        self.ensure_one()
        self.state = 'invoice'
        self.reserved_fleet_id.unlink()
        amounts = [
            (self.vehicle_id.name, self.rent_cost - self.first_payment - self._recurring_invoiced()),
            (_("Accessories/Tools"), self.tools_cost),
            (_("Damage/Tools missing cost"), self.damage_cost),
        ]
        lines = [self._invoice_line(name, amount) for name, amount in amounts if amount]
        if lines:
            return self._invoice_action(self._create_invoice(lines))

    def action_view_invoice(self):
        self.ensure_one()
        invoices = self.env['account.move'].search([('fleet_rent_id', '=', self.id)])
        if not invoices:
            return False
        if len(invoices) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Invoice'),
                'res_model': 'account.move',
                'view_mode': 'form',
                'view_id': self.env.ref('account.view_move_form').id,
                'res_id': invoices.id,
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('fleet_rent_id', '=', self.id)],
        }

    # -- calendar -----------------------------------------------------------------------------------

    def _calendar_event_values(self, kind):
        """Values of the pick-up ('start') or drop-off ('end') event."""
        self.ensure_one()
        if kind == 'start':
            title, when, where, handler = _("Pick up"), self.rent_start_date, self.pickup_location, self.handle_pickup
        else:
            title, when, where, handler = _("Drop off"), self.rent_end_date, self.dropoff_location, self.handle_dropoff
        rows = [
            (_("Vehicle"), self.vehicle_id.name),
            (_("Customer"), self.customer_id.name),
            (_("Customer Phone"), self.customer_id.phone),
            (_("Customer Mobile"), self.customer_id.mobile),
            (_("Driver"), self.driver_id.name),
            (_("Driver Phone"), self.driver_id.phone),
            (_("Driver Mobile"), self.driver_id.mobile),
        ]
        if kind == 'start':
            rows.append((_("Deposit"), self.car_deposit))
        rows.append((title, "%s (%s)" % (where, when)))
        if kind == 'start':
            rows.append((_("Obs"), self.notes))
        description = Markup("<br/>").join(Markup("%s : %s") % (label, value or '')
                                           for label, value in rows)
        alarms = self.env['calendar.alarm'].search([('duration', '=', 1), ('interval', '=', 'days')])
        return {
            'name': "%s : %s" % (title, self.vehicle_id.name),
            'location': where,
            'start': when - timedelta(minutes=30),
            'stop': when,
            'duration': 0.5,
            'allday': False,
            'show_as': 'free',
            'partner_ids': [Command.set((self.sales_person | handler).ids)],
            'alarm_ids': [Command.set(alarms.ids)],
            'description': description,
        }

    def _sync_calendar_event(self, kind):
        """Create or update one event; skip the write when nothing changed."""
        self.ensure_one()
        event_field, hash_field = 'calendar_%s_date_id' % kind, 'calendar_%s_date_hash' % kind
        values = self._calendar_event_values(kind)
        digest = hashlib.sha256(json.dumps(values, default=str, sort_keys=True).encode()).hexdigest()
        event = self[event_field]
        if event and self[hash_field] == digest:
            return
        Event = self.env['calendar.event'].with_user(SUPERUSER_ID).with_context(mail_notify_author=True)
        if event:
            Event.browse(event.id).write(values)
        else:
            event = Event.create(values)
        self.sudo().write({event_field: event.id, hash_field: digest})

    def _calendar_sync_enabled(self):
        return bool(self._get_param('fleet_rental_calendar_sync'))

    def sync_calendar_start(self):
        if self._calendar_sync_enabled():
            for contract in self.filtered(lambda c: c.state in ('reserved', 'running')):
                contract._sync_calendar_event('start')

    def sync_calendar_end(self):
        if self._calendar_sync_enabled():
            for contract in self.filtered(lambda c: c.state in ('reserved', 'running')):
                contract._sync_calendar_event('end')

    def _sync_calendar(self):
        """Keep the pick-up and drop-off events in line with the contract:
        the pick-up event until the car is picked up, the drop-off event
        until it is returned."""
        self.filtered(lambda c: c.state == 'reserved').sync_calendar_start()
        self.sync_calendar_end()

    # -- documents ----------------------------------------------------------------------------------

    def _get_contract_filename(self):
        return ("contract_%s.pdf" % self.name.replace('/', '_')).lower()

    def _get_reserve_filename(self):
        return ("reserve_%s.pdf" % self.name.replace('/', '_')).lower()

    def action_generate_contract(self):
        """Render the contract PDF and attach it, replacing the previous one."""
        self._check_manage_rights()
        Attachment = self.env['ir.attachment'].sudo()
        for contract in self:
            filename = contract._get_contract_filename()
            Attachment.search([('res_model', '=', self._name), ('res_id', '=', contract.id),
                               ('name', '=', filename)]).unlink()
            pdf, _report_type = self.env['ir.actions.report'].with_context(
                force_report_rendering=True)._render_qweb_pdf(
                'fleet_rental.car_rental_contract_pdf', res_ids=contract.ids)
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(pdf),
                'res_model': self._name,
                'res_id': contract.id,
                'mimetype': 'application/pdf',
            })
            contract.attachment_ids = [Command.link(attachment.id)]

    def action_save_pickup(self):
        self.ensure_one()
        return True
