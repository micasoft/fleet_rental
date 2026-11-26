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
from odoo import fields, models, tools

from ..models.car_rental_contract import COST_FREQUENCIES, STATES


class FleetRentalReport(models.Model):
    """Rental analysis: one row per (not deleted) contract."""
    _name = "report.fleet.rental"
    _description = "Fleet Rental Analysis"
    _order = 'name desc'
    _auto = False

    name = fields.Char(string="Name")
    customer_id = fields.Many2one('res.partner')
    vehicle_id = fields.Many2one('fleet.vehicle')
    rent_cost = fields.Float(string="Rent Cost")
    rent_start_date = fields.Date(string="Rent Start Date")
    rent_end_date = fields.Date(string="Rent End Date")
    state = fields.Selection(STATES, string="State")
    cost_frequency = fields.Selection(COST_FREQUENCIES, string="Recurring Cost Frequency")
    total = fields.Float(string="Total(Tools)")
    damage_cost = fields.Float(string="Damage cost")
    total_cost = fields.Float(string="Total cost")

    def init(self):
        tools.sql.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW report_fleet_rental AS
            SELECT t.id,
                   t.name,
                   t.customer_id,
                   t.vehicle_id,
                   t.rent_cost,
                   t.rent_start_date,
                   t.rent_end_date,
                   t.state,
                   t.cost_frequency,
                   t.tools_cost AS total,
                   t.damage_cost,
                   t.total_cost
              FROM car_rental_contract t
             WHERE NOT COALESCE(t.soft_deleted, FALSE)
        """)
