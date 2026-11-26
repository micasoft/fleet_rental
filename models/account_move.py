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
from markupsafe import Markup

from odoo import fields, models, _


class AccountMove(models.Model):
    """Link invoices to their rental contract."""
    _inherit = 'account.move'

    fleet_rent_id = fields.Many2one('car.rental.contract', string='Rental',
                                    help='Rental contract this invoice belongs to')
    is_first_invoice = fields.Boolean(string='Is First Rental Invoice', default=False,
                                      help='Invoice of the first payment of a rental')

    def button_cancel(self):
        """Cancelling a rental invoice updates its contract:
        - the first invoice can be created again;
        - the final invoice sends an invoiced contract back to checking;
        - a recurring invoice changes nothing;
        - a done or cancelled contract never changes."""
        result = super().button_cancel()
        for move in self.filtered('fleet_rent_id'):
            contract = move.fleet_rent_id
            if contract.state in ('done', 'cancel'):
                continue
            if move.is_first_invoice:
                contract.first_invoice_created = False
            elif move in contract.recurring_line.invoice_ref:
                continue
            elif contract.state == 'invoice':
                contract.state = 'checking'
        return result

    def _send_first_payment_mail(self):
        self.ensure_one()
        body = Markup(
            "<h3>%s</h3><p>%s</p><table>"
            "<tr><td>%s</td><td>%s</td></tr>"
            "<tr><td>%s</td><td>%s</td></tr>"
            "<tr><td>%s</td><td>%s</td></tr></table>"
        ) % (
            _("First Payment Received!"),
            _("Hi %s, this is to notify that your first payment has been received. "
              "Please find the details below:", self.partner_id.name),
            _("Invoice Number"), self.name,
            _("Date"), self.invoice_date or '',
            _("Amount"), self.amount_total,
        )
        self.env['mail.mail'].sudo().create({
            'subject': _("Payment Received: %s", self.name),
            'author_id': self.env.user.partner_id.id,
            'body_html': body,
            'email_to': self.partner_id.email,
        }).send()
