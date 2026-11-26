# Test suite for fleet_rental — design

## Intent

The addon is a fork that will be evolved (new features, bug fixes, security
fixes). Before any business logic changes, it needs an automated test suite
that states how the addon **should** behave, so every later change is checked
against it.

The user chose **correct-behaviour tests**: where the code is wrong today, the
test asserts the correct behaviour and fails until the bug is fixed. The
suite is therefore red on day one; each failing test is a documented bug.

## Goals

- `make test` runs the addon's tests on a fresh, throwaway database and exits
  non-zero if any test fails.
- Tests cover the business flows (quote → reserve → run → check → invoice →
  done), pricing, availability, invoicing, crons, calendar sync, security, and
  every bug found in the 2026-11-26 review (list below).
- Each test that fails today because of a bug says so in its docstring
  (`Bug: …`), so the red list doubles as the bug list.

## Non-goals

- No changes to addon Python/XML/CSV in this work. Bugs are recorded by
  tests, not fixed.
- No browser/JS (tour) tests, no PDF rendering tests (wkhtmltopdf needs
  `workers >= 2`), no performance tests.
- No CI pipeline yet (the setup must not prevent adding one later).

## Anti-goals

- Tests must never touch the LAN Postgres, `ptcarstesting`, `.env` or
  `.secrets/`. A test run that could land on real data is a failure even if
  the tests pass.
- Tests must not depend on production data or on the order they run in.

## Constraints

- Odoo 18 (`odoo:18` image, the same one the dev stack uses), Odoo's own test
  framework (`odoo.tests`: `TransactionCase`, `Form`, `tagged`, `new_test_user`,
  `freezegun` 1.2.1 is in the image), tests in `fleet_rental/tests/`.
- Limited RAM on this machine: the test database lives only during a run.
- Must not modify `.env` or anything under `.secrets/` (standing user rule).

## Approaches considered (user picked A)

- **A. Temporary Postgres container during `make test` (chosen).** A separate
  compose project starts `postgres` with its data on tmpfs, runs Odoo with
  `-i fleet_rental --test-enable`, then removes everything. Isolated, fresh
  every run, ~150 MB only while running, CI-ready.
- B. A test database on the LAN server, emptied before each run. No local
  RAM, but slower, needs a second DB and `.env` key, and a guard against
  pointing it at `PG_DATABASE`.
- C. Run tests inside the restored `ptcarstesting`. Rejected: depends on
  production data and runs test transactions inside the working copy.

## How it runs (decided)

- `docker-compose.test.yml`, compose project name `fleet_rental_test`,
  independent of the dev project (`fleet_rental_dev`) and of `.env`.
  - `db`: `postgres:17-alpine`, data on tmpfs, user/password `odoo`/`odoo`,
    healthcheck with `pg_isready`, **no published ports**.
  - `odoo`: `odoo:18`, the same `dev/entrypoint.sh` and `dev/odoo.conf`,
    repo mounted read-only at `/mnt/extra-addons/fleet_rental`, no extra
    addons mount, env set in the compose file (`PG_HOST=db`, `PG_PORT=5432`,
    `PG_USER=odoo`, `PG_DATABASE=fleet_rental_test`), secret from a committed
    file `dev/test/pg_password` containing `odoo` (a throwaway password for a
    container that only exists on a private Docker network during the run).
  - The entrypoint is reused unchanged: Odoo creates the database itself
    (`_create_empty_database`) and returns a non-zero exit code when tests
    fail (verified in the image).
- `make test` = `docker compose -f docker-compose.test.yml run --rm odoo
  -i fleet_rental --test-enable --test-tags /fleet_rental --stop-after-init
  --log-level=test`, then `docker compose -f docker-compose.test.yml down -v`
  **always** (also on failure/Ctrl-C), exit code = the test run's.
- `make test TAGS=...` passes a custom `--test-tags` (e.g.
  `/fleet_rental:TestPricing`) to run a subset.
- Installing from scratch (base, account, fleet, mail, calendar, contacts)
  takes a few minutes; accepted.

## Test layout (builder's call within this frame)

- `tests/__init__.py` imports every test module.
- `tests/common.py`: `FleetRentalCommon(AccountTestInvoicingCommon)` creating
  a company with a chart of accounts, the service product with an income
  account (set as `fleet_rental_service_product_id`), a sales journal, a
  vehicle with an owner and rental cost ranges, customer/driver partners,
  tools, users in each group (Pickup/Dropoff, Normal, Administrator), and a
  `make_contract(**overrides)` helper.
- One file per area: pricing, availability/reservation, lifecycle and crons,
  invoicing, calendar, partner, security, report, vehicle cost ranges.
- Tests are `@tagged('post_install', '-at_install', 'fleet_rental')`.
- Date-dependent tests use `freezegun.freeze_time`, never the real date.
- Mail: assert queued `mail.mail` records / `message_ids`, never real sending
  (the test DB has no mail server).

## Behaviour the tests assert

"Today" means the frozen test date. Items marked **[call]** are decisions I
made where the code doesn't say what's correct; items marked **[user]** were
decided by the user on 2026-11-26.

**[user] Timezone:** "today", "tomorrow" and the day count use the company's
local time (the company user's `tz`, e.g. `Europe/Lisbon`), not UTC. Tests
include boundary cases around local midnight (e.g. a 00:30 local pickup in
summer, which is the previous day in UTC). Today the code uses UTC (bug).

### Pricing and duration (current behaviour is correct)

- `contract_days = (end − start − tolerance_hours).days + 1`, tolerance from
  `fleet_rental_tolerance_delay` (default 3). Cases: same day 10:00→18:00 = 1;
  10:00→next day 12:00 = 1; 10:00→next day 14:00 = 2; end = start = 0.
- End before start raises `UserError`.
- `car_cost_per_day` comes from the vehicle's cost range where
  `day_from <= contract_days <= day_to`; no matching range → 0.
- `rent_cost = car_cost_per_day × contract_days` while in Quote.
- Tools: `daily` → quantity = contract_days, `once` → 1;
  `tools_cost = Σ price × quantity`; `total_cost = rent + tools + damage`.
- Cost ranges: overlapping or `day_from >= day_to` raise on save.
  **[call]** A one-day range (`day_from == day_to`, e.g. 1–1) should be
  allowed; today it is refused (bug).

### Availability and reservation

- Confirming a quote whose dates overlap another reservation of the same
  vehicle raises `UserError`; adjacent (non-overlapping) periods are allowed.
- **[user]** Same-time handover is allowed: a reservation ending at 10:00 and
  the next starting at 10:00 on the same vehicle do not overlap, no buffer
  (today refused — bug).
- Confirm: state `reserved`, one `car.rental.reserved` with the contract's
  dates, name from sequence `RENT/<year>/NNNN` (year of the contract's
  creation date).
- **[call]** Moving back to Quote and confirming again keeps the same
  contract number (today a new number is drawn each time — bug).
- Cancel: removes the reservation and both calendar events; state `cancel`;
  vehicle state back to Active.
- Extend rent: new end date must be after the reserved end (else
  `ValidationError`); confirming updates the reservation's `date_to`;
  discarding restores the previous end date.
- **[user]** Extending into another reservation of the same vehicle raises
  `UserError`, like confirm (today allowed — bug).
- **[user]** Extending a reserved or running contract re-prices the rent for
  the new day count using the vehicle's cost ranges (today `rent_cost` only
  changes in Quote, so extra days are never billed — bug).

### Lifecycle and crons

- Running → vehicle state Rent; Cancel/Invoice → vehicle state Active.
- `fleet_scheduler` (daily cron): reserved with start ≤ today → running;
  running with end < today → checking; invoice → done.
- **[call]** A running contract whose end date is **today** stays running
  until the next day; its last period is still billed if it starts on or
  before the end date (recurring rules below).
- `next_event` (daily cron): queues the "next pickup" mail for reserved
  contracts starting tomorrow and the "next drop-off" mail for running
  contracts ending tomorrow. **[call]** It changes no contract state (today it
  calls `action_run` on an empty recordset — bug, no effect).
- **[call]** Field defaults use the date at the moment the record is created,
  not the date the server started (bug: `default=str(date.today())`).
- Crons and actions work on several contracts at once (writing `state` on two
  contracts in one call does not raise "Expected singleton" — bug).

### Invoicing

- Prerequisite: service product without income account (product or
  category) → `UserError` naming the product.
- `action_invoice_create` with `cost_frequency = 'no'`: one customer invoice
  for the contract, flagged `is_first_invoice`, one line = `first_payment`,
  linked by `fleet_rent_id`; `first_invoice_created` set.
- `action_invoice_create` with daily/weekly/monthly does not crash (bug:
  datetime vs date comparison and a wrong `strptime` format).
- **[user]** Recurring invoices (cron and `action_invoice_create` alike):
  - the first period is billed on the start date;
  - each later period is billed on the day it starts: daily = every day,
    weekly = every 7 days, monthly = the same day of each calendar month
    (a start on the 31st falls on the last day of shorter months);
  - never a period starting after the end date;
  - idempotent: running the cron twice the same day, or the cron after
    `action_invoice_create`, creates no duplicate for a period;
  - catch-up: a missed cron run is billed on the next run;
  - each invoice: one line named after the vehicle, amount
    `cost_generated`, partner = customer, invoice date = period start,
    linked by `fleet_rent_id` and listed in `recurring_line`.
  Today: weekly/monthly cron skip the first period, monthly is 30 days in
  the manual path, no idempotency, the cron path uses the empty model
  instead of the contract (bugs).
- `action_verify` (checking → invoice): reservation removed; final invoice
  lines: rent, tools (`tools_cost`), damage (`damage_cost`); lines with zero
  amount are omitted.
- **[user]** Final invoice total = rent + tools + damage − first payment −
  recurring invoices already issued (today recurring invoices are not
  subtracted, so a recurring contract is billed twice — bug).
- **[call]** Default journal is the company's sales journal (today: the
  journal with id 1 — bug).
- `invoice_count` and `action_view_invoice` show the contract's invoices.
- **[user]** Cancelling a rental invoice (`button_cancel`) depends on which
  invoice it is:
  - the first invoice → `first_invoice_created` back to False, so it can be
    created again;
  - the final invoice (from `action_verify`) of a contract in `invoice` →
    contract back to `checking`;
  - a recurring invoice → contract unchanged;
  - a `done` or `cancel` contract never changes state.
  - Cancelling several invoices at once, or one with no contract, works
    (bug: singleton).
  Today any cancel of a non-running contract's invoice moves it to
  `checking` (bug).
- First payment registered on a first invoice queues a "First Payment
  Received" mail to the customer. **[call]** The invoice is found from the
  payment's own reconciled invoices, not by searching invoice name =
  payment memo (fragile today).

### Calendar sync (`fleet_rental_calendar_sync` on)

- Reserving creates a pick-up and a drop-off event (30 min ending at the
  start/end time) with the salesperson and the handler as attendees; off →
  no events.
- Changing the handler, dates or customer phone updates the event; re-syncing
  an unchanged contract does not rewrite it.
- **[call]** The drop-off event's location is the drop-off location (today it
  uses the pick-up location — bug).
- Known bug not tested: the change-detection hash uses Python's `hash()`,
  which differs per process, so every restart rewrites all events. Recorded
  here; a test would need to restart Odoo.

### Partner

- Writing several partners in one call works (bug: `self.id` singleton) and
  re-syncs the calendar events of each one's reserved/running contracts.

### Pickup odometer

- Reading a contract creates no odometer record (bug: the compute creates
  one).
- Setting the pick-up kilometrage records an odometer value for the vehicle.

### Deletion and security

- **[call]** Deleting a contract keeps the soft-delete design (record hidden,
  `soft_deleted = True`, reservation and calendar events removed), but only
  users with delete rights (Administrator) may do it; a Pickup/Dropoff or
  Normal user gets `AccessError` (bug: the override skips the access check).
- Pickup/Dropoff user sees only reserved/running contracts where they handle
  pick-up or drop-off; Normal user sees all.
- **[user]** A Pickup/Dropoff user can change only the pick-up/drop-off
  fields: `rent_pickup_date`, `rent_dropoff_date`, `fuel_tunk_pickup`,
  `fuel_tunk_dropoff`, `meters_pickup_value`, `attachment_pickup_ids`,
  `signature_pickup`, `notes`. Writing any other field (e.g. `rent_cost`,
  `customer_id`, `state`) raises `AccessError` (today allowed — bug). Calling
  business actions (`action_confirm`, `action_verify`, `action_cancel`,
  invoicing) also raises `AccessError`.
- **[user]** All Fleet users see all vehicles (the core "own vehicles" rule
  stays replaced — intended).
- Tool names are escaped in the Accessories/Tools list
  (`<img src=x onerror=…>` appears as text, not HTML — bug: stored XSS).

### Report

- "Fleet Rental Analysis" (`report.fleet.rental`) can be read with every
  field; rent cost and tools total match the contract; every contract state
  is a valid selection value (bug: wrong column names, missing states).
- Every model has access rules (`report.fleet.rental` has none today).

## Left to the builder

- Exact test names, fixture values, file split, helper signatures.
- How to assert queued mails (by template subject or `mail.mail` model/res_id).
- Whether a bug needs one test or several to pin it.
