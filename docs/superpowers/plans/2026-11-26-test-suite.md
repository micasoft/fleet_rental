# fleet_rental Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `make test` runs a correct-behaviour test suite for `fleet_rental` on a throwaway Postgres; tests for known bugs fail by design.

**Architecture:** A separate compose project (`docker-compose.test.yml`, project `fleet_rental_test`) runs `postgres:17-alpine` on tmpfs plus the `odoo:18` image with the existing `dev/entrypoint.sh`. A host script `dev/run-tests` installs the module with `--test-enable` and always tears the project down. Tests live in `tests/`, built on `AccountTestInvoicingCommon`.

**Tech Stack:** Odoo 18 test framework (`odoo.tests`: `TransactionCase`, `Form`, `tagged`, `new_test_user`), `freezegun` 1.2.1, `odoo.addons.mail.tests.common.MockEmail`, Docker Compose v2, Bash, GNU Make.

**Spec:** `docs/superpowers/specs/2026-11-26-test-suite-design.md`

## Global Constraints

- No changes to addon Python/XML/CSV/JS (`models/`, `views/`, `data/`, `security/`, `reports/`, `wizard/`, `static/`, `__manifest__.py`). Only `tests/`, the test runner files, `Makefile`, `README.rst`, docs.
- Never read, create, edit or delete `.env` or anything under `.secrets/`. The test stack must not use `env_file` or the dev secret.
- Never connect to the LAN Postgres or `ptcarstesting`.
- Tests are `@tagged('post_install', '-at_install', 'fleet_rental')`.
- Date-dependent tests use `freezegun.freeze_time`; never the real date.
- Local time = the acting user's `tz`; tests set `tz = 'Europe/Lisbon'` on the test users **and** on `base.user_root` (the cron user).
- Each test that fails today has a docstring line `Bug: <one line>` naming the bug (spec wording).
- Mail is captured with `MockEmail.mock_mail_gateway()`; no real sending.

## Rulings made while planning (additions to the spec)

- **Fresh install has no `fleet_rental_tolerance_delay` parameter** (the settings default is only written when Settings are saved), so `int(None)` crashes the day count. Correct: missing parameter = 3. Test in Task 2. Cost if wrong: one extra red test.
- **Fresh install has no `fleet_rental_service_product_id`**, and the setting stores a `product.template` id while the code searches `product.product` by that id. Correct: missing parameter falls back to `fleet_rental.fleet_service_product`; a configured template is used through its variant. Tests in Task 5. Cost if wrong: two extra red tests.
- **Day count across timezones is not tested** separately: the count is a time difference and only changes across DST; the timezone rule is tested where it matters (cron "today/tomorrow" boundaries, Task 4).

## Review Focus

1. A test run when `.env` exists → still connects only to the `db` container (Task 1, Step 6).
2. Ctrl-C or a failing run → no `fleet_rental_test` containers/volumes left (Task 1, Step 6).
3. An error in a test class's setup → the run exits non-zero and the error is visible, not silently skipped (Task 1, Step 5).
4. Running `make test` while the dev stack (`make up`) runs → dev server keeps running, no port clash (Task 1, Step 6).
5. A test passing only because of the real date or test order → every date-bound test is frozen; `make test` twice gives the same pass/fail list (Task 8, Step 2).

---

### Task 1: Test runner, fixtures and smoke test

**Files:**
- Create: `docker-compose.test.yml`, `dev/test/pg_password` (content `odoo`, no newline), `dev/run-tests` (executable), `tests/__init__.py`, `tests/common.py`, `tests/test_smoke.py`
- Modify: `Makefile` (add `test`, `help` line), `README.rst` ("Running the tests" section)

**Interfaces:**
- Produces: `make test [TAGS=<test-tags>] [KEEP=1]`; exit code = Odoo's.
- Produces (`tests/common.py`): class `FleetRentalCommon(AccountTestInvoicingCommon)` with class attributes `company`, `customer`, `driver`, `owner`, `vehicle`, `vehicle2`, `tool_once` (price 10, unit once), `tool_daily` (price 5, unit daily), `service_product` (product.product, no taxes, income account set), `sales_journal`, `user_limited`, `user_normal`, `user_manager`; method `make_contract(self, **vals) -> car.rental.contract` (defaults: `customer_id`/`driver_id` = customer/driver, `vehicle_id` = vehicle, `pickup_location='Porto'`, `dropoff_location='Lisboa'`, `rent_start_date='2026-03-02 10:00:00'`, `rent_end_date='2026-03-05 10:00:00'`, `rent_cost=150`, `first_payment=50`, `cost_frequency='no'`); `confirm(contract)` helper calling `action_confirm`.
- `vehicle` cost ranges: 1–3 days @ 50, 4–10 days @ 40. `vehicle2` has no ranges.
- Config params set in `setUpClass`: `fleet_rental_tolerance_delay=3`, `fleet_rental_service_product_id=<service_product.product_tmpl_id.id>`, calendar sync off, booking/recurring mails off. Users and `base.user_root` get `tz='Europe/Lisbon'`. Users belong to `company`.

- [ ] **Step 1: Write `tests/test_smoke.py`** — `TestSmoke(FleetRentalCommon)`: `test_module_installed` (module state `installed`), `test_fixture_contract` (`make_contract()` has state `draft`, name `Quote Contract`).

- [ ] **Step 2: Run before the runner exists** — `make test` → Expected: `make: *** No rule to make target 'test'`.

- [ ] **Step 3: Implement the runner**
  - `docker-compose.test.yml`: `name: fleet_rental_test`; `db`: `postgres:17-alpine`, `POSTGRES_USER/PASSWORD=odoo`, `POSTGRES_DB=fleet_rental_test`, data dir on `tmpfs`, `pg_isready` healthcheck, no `ports`; `odoo`: `odoo:18`, `user: root`, entrypoint `/dev-entrypoint.sh`, `environment` `PG_HOST=db PG_PORT=5432 PG_USER=odoo PG_DATABASE=fleet_rental_test`, secret `pg_password` from `./dev/test/pg_password`, volumes: repo `:ro` at `/mnt/extra-addons/fleet_rental`, `dev/odoo.conf`, `dev/entrypoint.sh` (same targets as dev), a throwaway volume for `/var/lib/odoo`; `depends_on: db: condition: service_healthy`. No `env_file`.
  - `dev/run-tests` (`set -euo pipefail`): `trap` that runs `docker compose -f docker-compose.test.yml down -v --remove-orphans` on EXIT unless `KEEP=1`; runs `docker compose -f docker-compose.test.yml run --rm odoo <mode> fleet_rental --test-enable --test-tags "${TAGS:-/fleet_rental}" --stop-after-init --workers 0 --max-cron-threads 0 --log-level test`, where `<mode>` is `-u` if the DB already has `fleet_rental` installed (KEEP reuse; check via `docker compose exec -T db psql -U odoo -d fleet_rental_test -Atc "select 1 from ir_module_module where name='fleet_rental' and state='installed'"`, absent table = not installed) else `-i`; prints `N failed, M error(s)` summary line from Odoo's log tail and exits with Odoo's rc.
  - `Makefile`: `test:` → `@TAGS='$(TAGS)' KEEP='$(KEEP)' ./dev/run-tests` (does **not** depend on `check-env`).
  - `tests/__init__.py`, `tests/common.py` per Interfaces.

- [ ] **Step 4: Run** — `make test` → Expected: exit 0, log shows `TestSmoke` 2 tests, `0 failed, 0 error(s)`; afterwards `docker ps -a --filter label=com.docker.compose.project=fleet_rental_test -q` and `docker volume ls -q --filter label=com.docker.compose.project=fleet_rental_test` print nothing.

- [ ] **Step 5: Prove failures fail the run** — temporarily add `test_must_fail` (`self.fail('x')`) and a class whose `setUpClass` raises; `make test TAGS=/fleet_rental:TestSmoke` (and the broken class) → Expected: exit non-zero, both reported. Remove them.

- [ ] **Step 6: Isolation checks**
  - `docker compose -f docker-compose.test.yml config | grep -E 'PG_HOST|env_file'` → only `PG_HOST: db`.
  - With the dev stack up (`docker ps` shows `fleet_rental_dev-odoo-1`; do not start/stop it yourself — if it isn't running, skip and ledger it), run `make test TAGS=/fleet_rental:TestSmoke` → dev container still `Up` afterwards.
  - Start `make test`, Ctrl-C during install → no `fleet_rental_test` containers/volumes remain.
  - `make test KEEP=1 TAGS=/fleet_rental:TestSmoke` twice → second run uses `-u` and is faster; then `docker compose -f docker-compose.test.yml down -v`.

- [ ] **Step 7: README** — "Running the tests": `make test`, `TAGS=`, `KEEP=1`, that it uses a throwaway Postgres in RAM (no LAN, no `.env`), that tests check **correct** behaviour so failures listed with `Bug:` are known bugs.

- [ ] **Step 8: Commit** — `git add docker-compose.test.yml dev/test dev/run-tests Makefile README.rst tests && git commit -m "Add test runner and fixtures"`

### Task 2: Pricing, duration, cost ranges

**Files:** Create `tests/test_pricing.py` (`TestPricing`)

**Interfaces:** Consumes `FleetRentalCommon`, `make_contract`. Use `Form(self.env['car.rental.contract'])` for onchange-driven values.

- [ ] **Step 1: Write tests** (Form sets vehicle first, then dates):
  - `test_days_same_day` 2026-03-02 10:00→18:00 → `contract_days == 1`
  - `test_days_next_day_within_tolerance` 10:00→next day 12:00 → 1
  - `test_days_next_day_over_tolerance` 10:00→next day 14:00 → 2
  - `test_days_zero` end = start → 0
  - `test_end_before_start_raises` → `UserError`
  - `test_days_without_tolerance_param` — delete the param; 10:00→next day 12:00 → 1. `Bug: missing fleet_rental_tolerance_delay crashes (int(None)).`
  - `test_cost_per_day_from_range` 3 days → `car_cost_per_day == 50`, `rent_cost == 150`; 5 days → 40 / 200
  - `test_cost_per_day_no_range` `vehicle2` → 0 / 0
  - `test_tools_quantities_and_totals` 3 days, tools once+daily, damage 7 → quantities 1 / 3, `tools_cost == 25`, `total_cost == 150+25+7`
  - `test_range_overlap_rejected` adding 3–5 to `vehicle` → `UserError`
  - `test_range_inverted_rejected` 6–5 → `UserError`
  - `test_range_single_day_allowed` 11–11 → saved. `Bug: day_from == day_to is refused.`

- [ ] **Step 2: Run** `make test TAGS=/fleet_rental:TestPricing` → Expected FAIL exactly: `test_days_without_tolerance_param`, `test_range_single_day_allowed`; all others PASS. Any other outcome: investigate (test bug vs new finding; a new finding becomes a `Bug:` test + ledger ruling).
- [ ] **Step 3: Commit** — `git add tests && git commit -m "Test pricing and duration"`

### Task 3: Availability, reservation, extension

**Files:** Create `tests/test_reservation.py` (`TestReservation`)

- [ ] **Step 1: Write tests**
  - `test_confirm_creates_reservation` → state `reserved`, one `car.rental.reserved` with contract dates, name matches `^RENT/<create_date.year>/\d{4}$`
  - `test_overlap_refused` second contract 2026-03-04→06 on same vehicle → `UserError`
  - `test_adjacent_allowed` second 2026-03-06 10:00→08 → confirmed
  - `test_same_time_handover_allowed` second starts 2026-03-05 10:00 → confirmed. `Bug: same-time handover refused (inclusive overlap).`
  - `test_number_kept_after_back_to_quote` confirm, `action_move_to_quote`, confirm → same name. `Bug: a new sequence number is drawn on each confirm.`
  - `test_cancel_cleans_up` (calendar sync on) → no reservation, no events, state `cancel`, vehicle state `fleet_rental.vehicle_state_active`
  - `test_booking_mail_when_enabled` param `fleet_rental_send_booking` on → mail subject `Reservation for …` to the customer; off → none
  - `test_send_quote` free vehicle → `sent_quote` True and a `Renting quote for …` mail; vehicle booked in that period → `UserError`
  - `test_extend_requires_later_date` `action_extend_rent`, end = old end − 1 day → `ValidationError`
  - `test_extend_updates_reservation` end +2 days, `action_confirm_extend_rent` → reservation `date_to` updated, `read_only` False
  - `test_extend_discard_restores` → end date back to reserved `date_to`
  - `test_extend_into_other_reservation_refused` other contract reserved 2026-03-06→08, extend to 03-07 → `UserError`. `Bug: extension ignores other reservations.`
  - `test_extend_reprices_rent` 3 days (150) extended to 5 days → `rent_cost == 200`. `Bug: extension never re-prices the rent.`
- [ ] **Step 2: Run** `TAGS=/fleet_rental:TestReservation` → Expected FAIL exactly the four `Bug:` tests.
- [ ] **Step 3: Commit** — `git commit -m "Test availability, reservation and extension"`

### Task 4: Lifecycle, crons, defaults, multi-record

**Files:** Create `tests/test_lifecycle.py` (`TestLifecycle`)

- [ ] **Step 1: Write tests** (all under `freeze_time`; cron methods called as `self.env['car.rental.contract'].with_user(self.env.ref('base.user_root'))`):
  - `test_running_sets_vehicle_rent` / `test_cancel_and_invoice_set_vehicle_active` (vehicle `state_id`)
  - `test_scheduler_reserved_to_running` frozen 2026-03-02 12:00 UTC, start 03-02 10:00 → `running`
  - `test_scheduler_running_to_checking` frozen 03-06 12:00, end 03-05 → `checking`
  - `test_scheduler_end_today_stays_running` frozen 03-05 12:00, end 03-05 10:00 → `running`
  - `test_scheduler_invoice_to_done`
  - `test_scheduler_uses_local_date` frozen `2026-07-14 23:15:00` (UTC; 00:15 July 15 Lisbon), start `2026-07-15 08:00:00` → `running`. `Bug: cron uses UTC date.`
  - `test_next_event_pickup_tomorrow` frozen 03-01 12:00, reserved start 03-02 10:00 → one mail with subject `Next events for <name>!` to the template's recipients; `test_next_event_dropoff_tomorrow` analogous for running end
  - `test_next_event_uses_local_tomorrow` frozen `2026-07-14 23:15:00`, reserved start `2026-07-16 08:00:00` → pickup mail sent. `Bug: cron uses UTC date.`
  - `test_next_event_changes_no_state` reserved contracts starting in 5 days → states unchanged (passes today: the bug has no effect; keeps it from coming back in a fix)
  - `test_defaults_use_creation_date` `freeze_time('2030-01-15 10:00')`, `Form` new contract → `rent_start_date`, `rent_pickup_date`, `rent_dropoff_date` dates == 2030-01-15. `Bug: date defaults frozen at server start.`
  - `test_write_state_on_two_contracts` `(c1|c2).write({'state': 'running'})` → no error, both vehicles in Rent. `Bug: singleton in state constraint.`
  - `test_cancel_two_contracts` `(c1|c2).action_cancel()` → both `cancel`. `Bug: singleton.`
- [ ] **Step 2: Run** `TAGS=/fleet_rental:TestLifecycle` → Expected FAIL exactly the five `Bug:` tests.
- [ ] **Step 3: Commit** — `git commit -m "Test lifecycle and crons"`

### Task 5: Invoicing

**Files:** Create `tests/test_invoicing.py` (`TestInvoicing`)

**Interfaces:** Recurring invoices are identified as contract invoices that are neither `is_first_invoice` nor the final one; counted via `contract.recurring_line` and `account.move` `invoice_date`. Amounts compared on `amount_untaxed`.

- [ ] **Step 1: Write tests**
  - `test_no_income_account_raises` service product and its category without income account → `UserError` containing the product name
  - `test_service_product_param_missing_falls_back` delete param → first invoice line product = `fleet_rental.fleet_service_product`. `Bug: missing parameter breaks invoicing.`
  - `test_service_product_param_is_template` param = template id of a product whose template id ≠ variant id (create dummy multi-variant templates until they differ; assert that precondition) → invoice line `product_id.product_tmpl_id` = configured template. `Bug: template id searched as product.product id.`
  - `test_first_invoice` frequency `no` → one invoice, `is_first_invoice`, one line 50, `fleet_rent_id`, `first_invoice_created`
  - `test_recurring_daily` start 03-02 10:00, end 03-05 10:00, `cost_generated=100`, frozen 03-05 12:00, `action_invoice_create` → recurring invoices dated 03-02, 03-03, 03-04, 03-05, each 100, line name = vehicle name, partner = customer. `Bug: crashes for recurring frequencies.`
  - `test_recurring_weekly` start 03-02, end 03-20, frozen 03-20 → 03-02, 03-09, 03-16. `Bug.`
  - `test_recurring_monthly_end_of_month` start 2026-01-31, end 04-15, frozen 04-15 → 01-31, 02-28, 03-31. `Bug.`
  - `test_recurring_cron_bills_contract` running daily contract, frozen 03-03 12:00, `fleet_scheduler` → invoices for 03-02 and 03-03 (catch-up), line name = vehicle name. `Bug: cron path uses the empty model.`
  - `test_recurring_idempotent` `action_invoice_create` then `fleet_scheduler` twice same day → no duplicate dates. `Bug.`
  - `test_recurring_reminder_mail` param on, cron bills → one mail for the contract (`model='car.rental.contract'`, `res_id=contract.id`). `Bug: send_mail on empty id.`
  - `test_final_invoice_lines` rent 150, first 50, tools 25, damage 30 → lines 100 / 25 / 30; reservation removed; state `invoice`
  - `test_final_invoice_omits_zero_lines` no tools, no damage → one line
  - `test_final_invoice_subtracts_recurring` rent 300, first 50, two recurring of 100 already issued, tools 20, damage 30 → `amount_untaxed == 100`. `Bug: recurring invoices billed twice.`
  - `test_default_journal_is_sales` new contract → `journal_type.type == 'sale'` and `journal_type.company_id == company`. `Bug: journal id 1.`
  - `test_invoice_count_and_view` 2 invoices → `invoice_count == 2`, `action_view_invoice()` domain on `fleet_rent_id`
  - `test_cancel_first_invoice_resets_flag` running contract → `first_invoice_created` False
  - `test_cancel_final_invoice_back_to_checking` contract `invoice` → `checking`
  - `test_cancel_recurring_invoice_keeps_state` contract `invoice`, cancel a recurring one → stays `invoice`. `Bug.`
  - `test_cancel_invoice_of_done_contract` → stays `done`. `Bug.`
  - `test_cancel_two_invoices` `(inv1|inv2).button_cancel()` → no error. `Bug: singleton.`
  - `test_cancel_invoice_without_contract` plain customer invoice → cancels, no error
  - `test_first_payment_mail_default_memo` post first invoice, register payment (default memo) → mail with subject `Payment Received: …` to the customer
  - `test_first_payment_mail_custom_memo` memo `XYZ` → same mail. `Bug: invoice looked up by name = memo.`
- [ ] **Step 2: Run** `TAGS=/fleet_rental:TestInvoicing` → Expected FAIL exactly the `Bug:` tests (14). `test_first_invoice`, `test_final_invoice_*` (except subtracts), `test_no_income_account_raises`, `test_invoice_count_and_view`, `test_cancel_first_invoice_resets_flag`, `test_cancel_final_invoice_back_to_checking`, `test_cancel_invoice_without_contract`, `test_first_payment_mail_default_memo` PASS.
- [ ] **Step 3: Commit** — `git commit -m "Test invoicing"`

### Task 6: Calendar, partner, odometer

**Files:** Create `tests/test_calendar.py` (`TestCalendar`), `tests/test_partner_odometer.py` (`TestPartnerOdometer`)

- [ ] **Step 1: Write tests** (calendar sync param on)
  - `test_reserve_creates_events` → pick-up event `start = start − 30 min`, `stop = start`, attendees include salesperson and `handle_pickup`; drop-off event analogous with `handle_dropoff`
  - `test_sync_off_no_events`
  - `test_dropoff_event_location` → drop-off event `location == 'Lisboa'`. `Bug: uses pickup location.`
  - `test_handler_change_updates_event` new `handle_dropoff` → attendees updated
  - `test_unchanged_resync_does_not_write` `mock.patch.object` on `calendar.event` `write` (wrapping the original) → not called on `sync_calendar_end()` with nothing changed
  - `test_write_two_partners` `(customer|driver).write({'phone': '+351 900 000 000'})` → no error; customer's reserved contract pick-up event description contains the new phone. `Bug: singleton in res.partner.write.`
  - `test_reading_creates_no_odometer` count `fleet.vehicle.odometer` before/after reading `meters_pickup_value` of a new contract → equal. `Bug: compute creates odometer.`
  - `test_set_pickup_km_records_odometer` `meters_pickup_value = 1234` → an odometer of `vehicle` with value 1234
- [ ] **Step 2: Run** `TAGS=/fleet_rental:TestCalendar,/fleet_rental:TestPartnerOdometer` → Expected FAIL exactly the three `Bug:` tests.
- [ ] **Step 3: Commit** — `git commit -m "Test calendar sync, partner and odometer"`

### Task 7: Security, deletion, report

**Files:** Create `tests/test_security.py` (`TestSecurity`), `tests/test_report.py` (`TestReport`)

- [ ] **Step 1: Write tests**
  - `test_limited_sees_own_reserved_running` limited user handling pick-up of a reserved contract sees it; not a draft one handled by them; not a reserved one handled by someone else
  - `test_normal_sees_all`
  - `test_limited_can_write_pickup_fields` each of `rent_pickup_date`, `rent_dropoff_date`, `fuel_tunk_pickup`, `fuel_tunk_dropoff`, `meters_pickup_value`, `attachment_pickup_ids`, `signature_pickup`, `notes` → succeeds
  - `test_limited_cannot_write_other_fields` `rent_cost`, `customer_id`, `state` (subTest each) → `AccessError`. `Bug: limited group can write every field.`
  - `test_limited_cannot_run_actions` `action_confirm`, `action_verify`, `action_cancel`, `action_invoice_create` (subTest each, on a contract they can see) → `AccessError`. `Bug` only for those that don't raise today (record which in the docstring after the first run).
  - `test_manager_delete_is_soft` → `soft_deleted` True (read with `sudo().with_context(active_test=False)` via SQL if the rule hides it), not found by `search`, reservation and events removed; works on two contracts at once
  - `test_normal_and_limited_cannot_delete` (subTest) → `AccessError`. `Bug: unlink override skips the access check.`
  - `test_fleet_user_sees_all_vehicles` user only in `fleet.fleet_group_user` sees a vehicle driven by someone else
  - `test_tool_name_escaped` tool name `<img src=x onerror=alert(1)>` → `list_line_tools` contains `&lt;img` and not `<img`. `Bug: stored XSS.`
  - `TestReport.test_report_reads_all_fields` `search_read` with `rent_cost`, `total`, `damage_cost`, `total_cost` → values match contract. `Bug: wrong column names.`
  - `TestReport.test_report_states_match_contract` selection keys equal. `Bug.`
  - `TestReport.test_every_model_has_access_rules` every non-abstract, non-transient model of module `fleet_rental` has ≥ 1 `ir.model.access`. `Bug: report.fleet.rental has none.`
- [ ] **Step 2: Run** `TAGS=/fleet_rental:TestSecurity,/fleet_rental:TestReport` → Expected FAIL exactly the `Bug:` tests.
- [ ] **Step 3: Commit** — `git commit -m "Test security, deletion and report"`

### Task 8: Full run and bug list

**Files:** Modify `README.rst` (link the bug list), Create `tests/KNOWN_BUGS.md`

- [ ] **Step 1: Run** `make test` → Expected: non-zero exit; every failing/erroring test has a `Bug:` docstring; no failure outside that set; no error in `setUpClass`.
- [ ] **Step 2: Run** `make test` again → Expected: identical pass/fail list.
- [ ] **Step 3: Write `tests/KNOWN_BUGS.md`** — table: test id, bug, file/line in the addon; generated from the run; header says the list must shrink to zero as fixes land.
- [ ] **Step 4: Commit** — `git commit -m "Record known bugs from the test suite"`
