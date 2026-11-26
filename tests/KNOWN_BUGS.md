# Known bugs (pinned by failing tests)

`make test` currently reports 40 failing tests out of 91; `make test-check` passes
when exactly these fail. Each one asserts the
**correct** behaviour (design: `docs/superpowers/specs/2026-11-26-test-suite-design.md`)
and carries a `Bug:` docstring. When a bug is fixed, its test turns green;
remove its row here in the same commit. This list must shrink to zero.

Line numbers refer to the code at the time the list was written (2026-11-26).

## Pricing and duration

| Test | Bug | Where |
|---|---|---|
| `TestPricing.test_days_without_tolerance_param` | Without the `fleet_rental_tolerance_delay` setting (fresh install, Settings never saved) the tolerance is 0 hours instead of 3. | `models/car_rental_contract.py:327` |
| `TestPricing.test_range_single_day_allowed` | A one-day price range (e.g. 11–11) is refused. | `models/car_rental_vehicle_cost.py:52` |

## Reservation and extension

| Test | Bug | Where |
|---|---|---|
| `TestReservation.test_confirm_assigns_number` | The contract sequence belongs to the company active at install; contracts of other companies get no number. | `data/fleet_rental_data.xml` (sequence without `company_id`), `models/car_rental_contract.py:646` |
| `TestReservation.test_number_kept_after_back_to_quote` | Back to Quote and confirmed again draws a new number. | `models/car_rental_contract.py:645` |
| `TestReservation.test_same_time_handover_allowed` | A return and the next pickup at the same time are treated as overlapping. | `models/car_rental_contract.py:275` |
| `TestReservation.test_extend_into_other_reservation_refused` | Extending ignores the vehicle's other reservations. | `models/car_rental_contract.py:807` |
| `TestReservation.test_extend_reprices_rent` | Extending never re-prices the rent; extra days are not billed. | `models/car_rental_contract.py:807` |

## Lifecycle and crons

| Test | Bug | Where |
|---|---|---|
| `TestLifecycle.test_scheduler_uses_local_date` | The daily cron uses the UTC date, not the company's local date. | `models/car_rental_contract.py:400` |
| `TestLifecycle.test_next_event_uses_local_tomorrow` | The reminder cron's "tomorrow" is the UTC tomorrow. | `models/car_rental_contract.py:431` |
| `TestLifecycle.test_scheduler_local_start_date` / `test_next_event_local_start_date` | The crons take the rental's date in UTC: a 00:30 local pickup counts as the previous day. | `models/car_rental_contract.py:394,434` |
| `TestLifecycle.test_defaults_use_creation_date` | Date defaults are fixed when the server starts. | `models/car_rental_contract.py:93,196,228` |
| `TestLifecycle.test_write_state_on_two_contracts` | Writing the state of several contracts at once crashes. | `models/car_rental_contract.py:346` |
| `TestLifecycle.test_cancel_two_contracts` | Cancelling several contracts at once crashes. | `models/car_rental_contract.py:653` |

## Invoicing

| Test | Bug | Where |
|---|---|---|
| `TestInvoicing.test_no_income_account_raises` | `for _ in range(...)` shadows the translation function; the "define an income account" message crashes with `UnboundLocalError`. | `models/car_rental_contract.py:732` |
| `TestInvoicing.test_service_product_param_missing_falls_back` | Without the service product setting (fresh install) invoicing crashes; it should use the module's service product or ask to configure one. | `models/car_rental_contract.py:485,544,762` |
| `TestInvoicing.test_service_product_param_is_template` | The setting stores a template id; the code searches product variants by it (wrong product). | same lines |
| `TestInvoicing.test_recurring_daily` / `_weekly` / `_monthly_end_of_month` | `action_invoice_create` crashes for recurring contracts (datetime vs date); months are 30 days. | `models/car_rental_contract.py:726` |
| `TestInvoicing.test_recurring_cron_bills_contract` | The cron's recurring path uses the empty model (`self.vehicle_id`) instead of the contract; its invoice date defaults to the day the server started; missed days are not caught up. | `models/car_rental_contract.py:479-532` |
| `TestInvoicing.test_cron_bills_contract_of_other_company` | The cron reads company-dependent values (income account) in the cron user's company, not the contract's ("Incompatible companies"). | `models/car_rental_contract.py:479-517`, `data/ir_cron_data.xml` |
| `TestInvoicing.test_recurring_idempotent` | Billing again the same day creates duplicate recurring invoices. | `models/car_rental_contract.py:404-416,716` |
| `TestInvoicing.test_recurring_reminder_mail` | The recurring reminder is sent for the empty model (`send_mail(self.id)`). | `models/car_rental_contract.py:532` |
| `TestInvoicing.test_final_invoice_subtracts_recurring` | The final invoice does not subtract recurring invoices already issued (billed twice). | `models/car_rental_contract.py:563` |
| `TestInvoicing.test_default_journal_is_sales` | The default journal is the one with id 1, whatever its type or company. | `models/car_rental_contract.py:132` |
| `TestInvoicing.test_cancel_recurring_invoice_keeps_state` | Cancelling a recurring invoice sends the contract back to Checking. | `models/account_move.py:47` |
| `TestInvoicing.test_cancel_invoice_of_done_contract` | Cancelling an invoice of a Done contract sends it back to Checking. | `models/account_move.py:47` |
| `TestInvoicing.test_cancel_two_invoices` | Cancelling invoices of several contracts at once crashes. | `models/account_move.py:43` |
| `TestInvoicing.test_first_payment_mail_custom_memo` | The paid invoice is found by name = payment memo; with any other memo no mail is sent. | `wizard/account_payment_register.py:32` |

## Calendar, contacts, odometer

| Test | Bug | Where |
|---|---|---|
| `TestCalendar.test_dropoff_event_location` | The drop-off event uses the pick-up location. | `models/car_rental_contract.py:915` |
| `TestPartnerOdometer.test_write_two_partners` | Saving several contacts at once (mass edit, import, merge) crashes. | `models/res_partner.py:30` |
| `TestPartnerOdometer.test_reading_creates_no_odometer` | Reading a contract creates an odometer record. | `models/car_rental_contract.py:450` |
| `TestPartnerOdometer.test_set_pickup_km_records_odometer` | Setting the pick-up km on a contract never read before loses the value. | `models/car_rental_contract.py:460` |

## Security and report

| Test | Bug | Where |
|---|---|---|
| `TestSecurity.test_limited_cannot_write_other_fields` | Pickup/Dropoff users can write every contract field. | `security/ir.model.access.csv:2` |
| `TestSecurity.test_normal_and_limited_cannot_delete` | The `unlink` override never checks delete rights; a Normal user can (soft-)delete. | `models/car_rental_contract.py:981` |
| `TestSecurity.test_tool_name_escaped` | Tool names are rendered unescaped (stored XSS). | `models/car_rental_contract.py:470` |
| `TestReport.test_report_reads_all_fields` | The analysis report's SQL view uses wrong column names. | `reports/report_fleet_rental.py:58,63` |
| `TestReport.test_report_states_match_contract` | The report's state list lacks Reserved and Invoice. | `reports/report_fleet_rental.py:37` |
| `TestReport.test_every_model_has_access_rules` | `report.fleet.rental` has no access rules. | `security/ir.model.access.csv` |

## Known bugs without a test

- Calendar change detection uses Python's `hash()`, which changes per process:
  every restart rewrites all calendar events (`models/car_rental_contract.py:886,926`).
  Testing it needs an Odoo restart.
- `unlink` is defined twice; the first definition (line 855) is dead code.
