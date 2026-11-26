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

from odoo import _, api, fields, models
from odoo.exceptions import UserError

class CarRentalVehicleCost(models.Model):
    _name = "car.rental.vehicle.cost"
    _description = "Vehicle range cost"
    _logger = logging.getLogger(__name__)
    company_currency_id = fields.Many2one(related='company_id.currency_id')

    vehicle_id = fields.Many2one('fleet.vehicle',
                                      string='Vehicle',
                                      help='Vehicle cost',
                                      ondelete='cascade')
    day_from = fields.Integer(string='From day')
    day_to = fields.Integer(string='To day')
    cost_per_day = fields.Monetary(string="Rent cost per day",
                        help="This fields is to determine the cost of rent per day",
                        currency_field='company_currency_id')

    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda self: self.env.company,
                                 help="Company this record owns")

    @api.constrains('day_from', 'day_to')
    def total_updater(self):
        """Each band starts at day 1 or later, ends on or after its start
        (a one-day band is fine) and overlaps no other band of the vehicle."""
        for vehicle in self.vehicle_id:
            seen = self.browse()
            for band in vehicle.rental_cost.sorted('day_from'):
                label = f"{band.day_from}-{band.day_to}"
                if band.day_from < 1:
                    raise UserError(_("Price band %s: 'From day' must be 1 or more.", label))
                if band.day_from > band.day_to:
                    raise UserError(_("Price band %s: 'From day' is after 'To day'.", label))
                for other in seen:
                    if other.day_from <= band.day_to and other.day_to >= band.day_from:
                        raise UserError(_("Price band %(band)s overlaps band %(other)s.",
                                          band=label, other=f"{other.day_from}-{other.day_to}"))
                seen |= band
