from odoo import fields, models

# Partner fields shown in the rental calendar events.
CALENDAR_PARTNER_FIELDS = {'name', 'phone', 'mobile'}


class CarRentalResPartner(models.Model):
    """Inherit res.partner"""
    _inherit = 'res.partner'

    person_id = fields.Char(string='ID/Passport')
    person_id_date = fields.Date(string="Issued at")
    person_id_until = fields.Date(string="ID/Passport until")
    person_id_issuer = fields.Char(string="Issued by")

    date_of_birth = fields.Date(string="Date of birth")
    birthplace = fields.Char(string="Birthplace")

    license = fields.Char(string="License")
    license_date = fields.Date(string="License at")
    license_until = fields.Date(string="License until")
    license_issuer = fields.Char(string="License by")

    is_agency = fields.Boolean(string="Is Rental Agency")

    def write(self, vals):
        result = super().write(vals)
        if CALENDAR_PARTNER_FIELDS & set(vals):
            contracts = self.env['car.rental.contract'].sudo().search([
                ('state', 'in', ['reserved', 'running']),
                '|', ('customer_id', 'in', self.ids), ('driver_id', 'in', self.ids),
            ])
            contracts._sync_calendar()
        return result
