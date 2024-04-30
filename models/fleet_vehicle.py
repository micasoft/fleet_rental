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
from odoo import fields, models


class CarRentalFleetVehicle(models.Model):
    """Inherit fleet.vehicle"""
    _inherit = 'fleet.vehicle'

    rental_reserved_time = fields.One2many('car.rental.reserved',
                                           'reserved_obj_id',
                                           string='Reserved Time',
                                           help='Reserved rental time',
                                           ondelete='cascade',
                                           readonly=True)
    
    fuel_type = fields.Selection(selection_add=[('gasoline', 'Gasoline'),
                                  ('diesel', 'Diesel'),
                                  ('electric', 'Electric'),
                                  ('hybrid', 'Hybrid'),
                                  ('petrol', 'Petrol')],
                                 string='Fuel Type', help='Fuel Used by the vehicle')
    
    cost_per_day = fields.Float(string="Rent cost per day",
                        help="This fields is to determine the cost of rent per day")

    deposit = fields.Float(string="Deposit value",
                        help="This fields is to determine the deposit value per day",
                        default=0)
    
    km_included_per_day = fields.Integer(string="Km(s) included",
                        help="The number of km included per day",
                        default=0)

    _sql_constraints = [('vin_sn_unique', 'unique (vin_sn)',
                         "Chassis Number already exists !"),
                        ('license_plate_unique', 'unique (license_plate)',
                         "License plate already exists !")]
