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

from odoo import models, fields, api
from odoo.exceptions import UserError

class CarRentalVehicleCost(models.Model):
    _name = "car.rental.vehicle.cost"
    _description = "Vehicle range cost"
    _logger = logging.getLogger(__name__)

    vehicle_id = fields.Many2one('fleet.vehicle',
                                      string='Vehicle',
                                      help='Vehicle cost',
                                      ondelete='cascade')
    day_from = fields.Integer(string='From day')
    day_to = fields.Integer(string='To day')
    cost_per_day = fields.Float(string="Rent cost per day",
                        help="This fields is to determine the cost of rent per day")

    @api.constrains('day_from', 'day_to')
    def total_updater(self):
        valid = True
        values = []
        for r in self.vehicle_id.rental_cost:
            self._logger.info(f"{r.day_from} >= {r.day_to}")
            if r.day_from >= r.day_to:
                valid = False
            for v in values:
                self._logger.error(f"{v[0]} <= {r.day_to} and {v[1]} >= {r.day_from}")
                if v[0] <= r.day_to and v[1] >= r.day_from:
                    valid = False
            values.append((r.day_from, r.day_to))
        if not valid:
            raise UserError(
                    'Something wrong with the range interval, please make sure the values are correct!')
