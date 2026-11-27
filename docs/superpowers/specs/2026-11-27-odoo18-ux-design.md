# Odoo 18 UX refresh — design

Date: 2026-11-27 · Release: 18.0.2.1.0 (minor: compatible, no migration)

## Intent

Bring every screen, report and email of fleet_rental to Odoo 18 conventions and
make it pleasant for the two kinds of people who use it:

- **Pickup/drop-off staff** work **on a phone**, standing at the car: they read
  the booking, record km, fuel, photos and the customer's signature.
- **Back office** works **on a desktop**: quotes, reservations, contracts,
  invoicing.

## Goals

1. A mobile-first **Pickup** screen and a new, matching **Drop-off** screen.
2. A cleaner back-office **contract** form, plus kanban, a real search view
   (filters, group-bys) and tidy list/calendar views.
3. Every other view (vehicle, partner, accessories, settings, analysis),
   both PDF reports and the five mail templates follow v18 markup.
4. Typos and odd labels fixed in the UI (strings), dead code removed.
5. `i18n/pt.po` updated for every string that changes or is added.

## Non-goals (this release)

- **No field renames, no migration** (that is "option 2", a later 18.0.3.0.0:
  `fuel_tunk_*`, `sales_person`, `handle_pickup`, `recurring_line`,
  `line_tools`, …). Field *labels* (`string=`) may change; technical names don't.
- **No other workflow change** than the two "Complete" buttons below: same
  states, same back-office buttons, same rights otherwise.
- **No new report content**: the two PDFs stay as they are (number only), only
  moved onto `web.external_layout`. Real contract/reservation content is later work.
- No step-by-step pickup assistant (option 3).

## Anti-goals

- A pickup user able to change anything outside `PICKUP_FIELDS` — the server
  check stays the authority, the views only mirror it.
- A phone screen that needs horizontal scrolling or pinch-zoom.
- Breaking existing data, tests (98/98) or the release tooling.

## Approaches considered

1. **Screens only** — rewrite views/reports/emails to v18, mobile-first pickup,
   additive drop-off fields, no renames. **Picked** (now).
2. Screens + model cleanup with renames and a migration — **later**, as its own
   release on top of 1.
3. Step-by-step pickup wizard (new transient model) — rejected for now: more
   code than "update to v18 standards", and 1 already makes the phone usable.

## Design

### Pickup and drop-off (phone)

- Menu *Rental Management ▸ Pickups* and *▸ Drop-offs* (pickup group).
  - Pickups: contracts `reserved`; Drop-offs: contracts `running`; the record
    rule already limits staff to the contracts they handle.
  - Default view **kanban** (one card per booking: vehicle + plate, customer,
    date/time, location, handler avatar), then list, calendar, form. Default
    filter "Today"; filters Today / Tomorrow / This week / Mine.
- Forms are a single column of plain groups (Odoo collapses them on phones),
  no nested groups, no inline styles:
  - read-only booking summary at top (vehicle, customer, drivers, date,
    location, accessories);
  - then the inputs: date/time, odometer value with its unit inline
    (`o_row`), fuel as a percentage (keep the `progressbar` widget, editable),
    photos (`many2many_binary` style widget accepting `image/*`, which opens
    the camera on phones), signature (full width), notes.
  - `create="0" delete="0"`, a proper title (`<h1>` with the contract number),
    no "Save Progress" button: the standard form save keeps work in progress
    (and `action_save_pickup` is removed once nothing references it).
- **Workflow (approved 2026-11-27)**: a primary header button on each form.
  - **Complete pickup** (`action_complete_pickup`, contract `reserved`):
    requires a pickup km value > 0 and the customer signature, then the
    contract becomes `running` (same effect as the back office's "Start the
    rental").
  - **Complete drop-off** (`action_complete_dropoff`, contract `running`):
    requires a drop-off km value ≥ the pickup km, then the contract becomes
    `checking`.
  - Both are allowed to pickup users on the contracts their record rule lets
    them write (`check_access('write')`), and to rental users; the state change
    itself is done with `sudo()` after that check, because `state` is not a
    pickup field. A missing requirement raises a `UserError` naming it. The
    chatter logs who completed it.
  - Once completed, the contract leaves the staff's Pickups/Drop-offs list
    (the domains filter on state).
- `send_contract` ("Send a contract to client") does nothing today and the
  contract PDF is still a stub: it is hidden from the pickup form (field kept)
  until the PDF has real content.
- **New additive fields for drop-off** (no migration needed, columns are created
  on update): `odometer_dropoff_id` + `meters_dropoff_value` (compute/inverse
  like the pickup pair, writing a `fleet.vehicle.odometer`),
  `meters_dropoff_unit`, `attachment_dropoff_ids` (own relation table),
  `signature_dropoff`. They are added to `PICKUP_FIELDS`. Fuel/date drop-off
  fields already exist.
- The back-office form shows pickup/drop-off results read-only in a
  "Pickup / Drop-off" notebook page.

### Back office (desktop)

- Contract form:
  - header: one primary button for the next step of the current state, the
    others secondary (`btn-secondary`); `statusbar_visible` showing the real
    flow (`draft,reserved,running,checking,invoice,done`); label typo fixed
    ("Start the rental").
  - sheet: smart button "Invoices" (`fa-pencil-square-o`), vehicle image as
    avatar, `oe_title`, two clean groups (*Customer*: customer, drivers,
    salesperson, company · *Booking*: vehicle, dates, locations, handlers),
    notebook pages *Pricing* (cost fields / recurring), *Accessories*,
    *Pickup / Drop-off*, *Documents* (attachments), *Notes*; totals footer
    in v18 style. `colors=` on the recurring list replaced by `decoration-*`.
  - `<chatter/>` kept.
- New **kanban** for contracts (grouped by state by default when opened as
  kanban), `t-name="card"` v18 template.
- **Search view**: fields (number, customer, driver, vehicle, plate),
  filters (Quotes, Reserved, Running, To check, To invoice, Done, Cancelled,
  In progress (default), Starting today, Returning today, My contracts),
  group-bys (state, vehicle, customer, salesperson, start month).
- List: `widget="badge"` state with decorations, monetary totals with `sum`,
  optional columns (`optional="show/hide"`).
- Calendar: keep, `color="vehicle_id"` (one colour per car is more useful than
  per state), state as filter.

### Other screens

- Vehicle form page: labels/groups tidied, reservation list read-only.
- Partner form: the ID/licence/birth block rebuilt with `o_row` and plain
  fields (no `width:49%` divs), shown only for individuals.
- Settings: v18 `<app string="Rental Management" name="fleet_rental">`,
  `<block>`, `<setting>`.
- Accessories: form/list tidied, `currency`-aware price if the field allows it
  (no type change).
- Analysis pivot: also graph view, sensible default measures/rows.

### Reports and emails

- Reports: `web.external_layout` instead of the custom `basic_layout`
  (company header/footer, paper format kept).
- Mail templates: company logo through `/logo.png?company=` instead of
  placehold.co, typos fixed ("This is to remind", `style=`, "next pickup(s)"
  template names), `format_datetime`/`format_amount` for dates and money.
  The templates are `noupdate`: existing databases keep their copies; this is
  noted in the release notes (reset from the template form if wanted).

### Dead code

- `static/src/xml/timepicker.xml` (not in assets, unused), commented-out
  vehicle view in `car_rental_contract_views.xml`, `action_save_pickup` after
  the form stops calling it.

## Testing

TDD where there is behaviour; for markup, tests that load the views:

- Each action's views load for its group (`get_views` as a pickup user and as
  a rental user) and the forms open in `odoo.tests.Form` with their view.
- Complete pickup/drop-off: state changes; refused without km/signature, with
  drop-off km below pickup km, in the wrong state, and for a pickup user on a
  contract they don't handle.
- Drop-off fields: writing `meters_dropoff_value` creates an odometer entry;
  a pickup user can write the drop-off fields and nothing else.
- Search filters produce the expected domains on fixture contracts.
- Settings form loads; both reports render; mail templates render.
- Full suite stays green (`make test-check`).

## Left to the builder

Exact icons, card layout details, group/page names, filter names and wording,
within the above.
