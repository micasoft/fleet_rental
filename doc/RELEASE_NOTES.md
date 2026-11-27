## Module <fleet_rental>

#### 27.11.2026
#### Version 18.0.2.1.0
#### UX refresh for Odoo 18
- Pickups and Drop-offs screens for the staff on their phone: cards for
  today's handovers, single-column forms with the booking on top, km, fuel,
  camera photos and the customer's signature.
- New "Complete pickup" (starts the rental) and "Complete drop-off" (moves the
  contract to Checking) buttons, usable by the Pickup/Dropoff users.
- Drop-off now records km, photos and the customer's signature.
- Contract form, list, kanban, calendar and search views rewritten for Odoo 18
  (one highlighted next step, status/date/salesperson filters, group-bys).
- Vehicle, contact, accessories, settings and analysis screens use Odoo 18
  markup; the analysis opens as a graph.
- PDFs use the company document layout; e-mails rewritten (no placeholder
  logo, formatted dates and amounts) and translated into Portuguese.
- Upgrade note: the e-mail templates are not overwritten on update
  (noupdate). To get the new texts on an existing database, open each
  "Car Rental: …" template in Settings ▸ Technical ▸ Email Templates and
  reset it, or delete it and update the module.


#### 06.03.2024
#### Version 17.0.1.0.0
#### ADD
- Initial Commit for Fleet Rental Management
