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
from odoo import api, fields, models


class CarRentalLineTools(models.Model):
    """Model to add the line tools of rental"""
    _name = 'car.rental.line.tools'
    _description = 'Car rental line tools model'

    name = fields.Many2one('car.rental.tools', string="Name",
                           help='Select car tools')

    contract_id = fields.Many2one('car.rental.contract',
                                       string="Checklist Number",
                                       help='Number of checklist')
    
    quantity = fields.Integer(string="Quantity",
                        default=1)
 
    unit = fields.Selection(related='name.unit', readonly=False)
    
    price = fields.Float(string="Price",
                         help='Price of the car tool')
    
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company,
                                 help="Company this record owns")

    @api.onchange('name')
    def onchange_name(self):
        """
           Update the price based on the selected name.
        """
        self.price = self.name.price
