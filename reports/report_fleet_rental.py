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
from odoo import models, fields, tools


class FleetRentalReport(models.Model):
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
    state = fields.Selection(
        [('draft', 'Draft'), ('running', 'Running'), ('cancel', 'Cancel'),
         ('checking', 'Checking'), ('done', 'Done')], string="State")
    cost_frequency = fields.Selection(
        [('no', 'No'), ('once', 'Full contract'), ('daily', 'Daily'), ('weekly', 'Weekly'),
         ('monthly', 'Monthly')], string="Recurring Cost Frequency")
    total = fields.Float(string="Total(Tools)")
    damage_cost = fields.Float(string="Damage cost")
    total_cost = fields.Float(string="Total cost")


    def _select(self):
        """
            Construct a SQL select query string with specific fields.
        """
        select_str = """
             SELECT
                    (select 1 ) AS nbr,
                    t.id as id,
                    t.name as name,
                    t.customer_id as customer_id,
                    t.vehicle_id as vehicle_id,
                    t.rent_cost as cost,
                    t.rent_start_date as rent_start_date,
                    t.rent_end_date as rent_end_date,
                    t.state as state,
                    t.cost_frequency as cost_frequency,
                    t.tools_cost as tools_cost,
                    t.damage_cost as damage_cost,
                    t.total_cost as total_cost
        """
        return select_str

    def _group_by(self):
        """
            Construct a SQL GROUP BY query string with specific fields.
        """
        group_by_str = """
                GROUP BY
                    t.id,
                    name,
                    customer_id,
                    vehicle_id,
                    rent_cost,
                    rent_start_date,
                    rent_end_date,
                    state,
                    cost_frequency,
                    tools_cost,
                    damage_cost,
                    total_cost
        """
        return group_by_str

    def init(self):
        """
            Initialize the module and create a database view for reporting
            fleet rentals.
            Drop the existing 'report_fleet_rental' view if it already exists.
            Create a new view with the SQL select and group by queries.
        """
        tools.sql.drop_view_if_exists(self._cr, 'report_fleet_rental')
        self._cr.execute("""
            CREATE view report_fleet_rental as
              %s
              FROM car_rental_contract t
                %s
        """ % (self._select(), self._group_by()))
