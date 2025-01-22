import logging
from odoo import models, fields


class CarRentalResPartner(models.Model):
    """Inherit res.partner"""
    _inherit = 'res.partner'

    _logger = logging.getLogger(__name__)

    person_id = fields.Char(string='ID/Passport')
    person_id_date = fields.Date(string="Issued at")
    person_id_issuer = fields.Char(string="Issued by")

    date_of_birth = fields.Date(string="Date of birth")
    birthplace = fields.Char(string="Birthplace")

    license = fields.Char(string="License")
    license_date = fields.Date(string="License at")
    license_until = fields.Date(string="License until")
    license_issuer = fields.Char(string="License by")

    is_agency = fields.Boolean(string="Is Rental Agency")

    def write(self, vals):
        r = super(CarRentalResPartner, self).write(vals)

        contracts = self.env['car.rental.contract'].sudo().search([
            ('customer_id.id', '=', self.id),
            ('state', 'in', ['reserved', 'running'])
        ])

        for contract in contracts:
            if contract.state == 'reserved':
                contract.sync_calendar_start()

            contract.sync_calendar_end()

        return r