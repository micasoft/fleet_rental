import logging
from odoo import models


class CarRentalResPartner(models.Model):
    """Inherit res.partner"""
    _inherit = 'res.partner'
    
    _logger = logging.getLogger(__name__)

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