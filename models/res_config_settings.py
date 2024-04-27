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


class ResConfigSettings(models.TransientModel):
    """Inherit configuration settings"""
    _inherit = 'res.config.settings'

    def _get_default_product(self):
        """
            Retrieve the default product ID for fleet services.
        """
        return self.env.ref('fleet_rental.fleet_service_product').id

    fleet_service_product_id = fields.Many2one(
        'product.template',
        string="Product",
        config_parameter='fleet_service_product_id',
        default=_get_default_product)

    fleet_rental_send_booking = fields.Boolean (
        string="Booking reserved",
        config_parameter='fleet_rental_send_booking',
        help="Enable to send a e-mail when the booking is reserved")

    fleet_rental_send_recurring_reminder = fields.Boolean (
        string="Recurring invoice",
        config_parameter='fleet_rental_send_recurring_reminder',
        help="Enable to send a e-mail about the recurring invoice")