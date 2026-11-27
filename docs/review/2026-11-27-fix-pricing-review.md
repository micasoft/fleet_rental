# Review: `fix-pricing` branch

Branch `fix-pricing`, built on `test-suite`. Nothing is pushed or merged yet.

| Commit | Subject |
|---|---|
| `5f2d3bd` | Fix pricing: default tolerance, one-day bands, refuse unpriced lengths |
| `a0a4b55` | Fix make test exit code: read Odoo's status, not the test's |
| `c1c5ffe` | Fix the known bugs and clean up the models |

To see the changes: `git diff test-suite fix-pricing` (26 files, +940 / −1288 lines).

## Verification

- **Test suite:** `make test-check` passes with 96 of 96 tests, 0 known bugs expected, 0 failing, and no fleet_rental warnings.
- **Upgrade path:**
  - I installed the old commit and then upgraded it with `-u` to the new code.
- **Not done:** no independent code review yet.

## Fixes by area

### Pricing (`5f2d3bd`)

- **Tolerance:** it has a default of 3 days in the code (`DEFAULT_TOLERANCE_DELAY`), so it applies even when the Settings were never saved.
- **One-day price bands:** a band like 11–11 is now allowed.
- **Checks on price bands**, done per vehicle. Each error message names the band:
  - "From day" must be at least 1;
  - "From day" must not be after "To day";
  - bands must not overlap.
- **Confirming without a price:** a contract can't be confirmed, or extended, when no price band covers its length.

### Reservations

- Prices are per day, so a vehicle serves one contract per day: a pickup on another contract's return day is refused, whatever the hour (local dates).
- **Extending a rental:**
  - it checks the car is free, excluding the contract's own reservation;
  - it re-prices the rent;
  - it updates daily tool quantities;
  - it checks a price band covers the new length.
- A contract keeps its number when it's confirmed again.
- **Contract numbers:** each company numbers its contracts on its own sequence, created on its first contract. The module's sequence stays the main company's.

### Daily jobs (`fleet_scheduler`, `next_event`)

- They use the local date. The time zone comes from the context, then the job user, then the company's contact, then UTC.
- They process several contracts at once.
- They skip deleted contracts.
- They invoice each contract with its own company's accounts.
- `next_event` only sends reminders; it no longer changes any state.

### Periodic billing

- The first invoice is on the start date. After that, invoices come daily, weekly, or on the same day each calendar month (`relativedelta`).
- Nothing is billed after the end date, and nothing is billed twice.
- Missed days are caught up.

### Final invoice

- It is: rent − first payment − periodic invoices already issued (cancelled ones don't count) + tools + damage.
- Lines worth zero are left out.

### Invoices and payments

- **Service product:** the right one is used. If the setting was never saved, the module's own product is used.
- **Journal:** the default is the company's sales journal.
- **Cancelling an invoice:**
  - for a first invoice, it resets the "first invoice created" flag;
  - for a periodic invoice, it changes nothing;
  - for a final invoice, the contract goes from "invoice" back to "checking";
  - for a contract that is done or cancelled, it changes nothing.
- **First-payment email:** it is found from the invoices actually paid, so a custom payment memo no longer stops it. Its body is escaped.
- **Editing an invoice line's price:** it updates the contract's first payment only on the first-payment invoice.

### Security

- Pickup/Dropoff users can only change the pickup and drop-off fields, and can't run any business action.
- Deleting a contract checks access rights. The car is released, and the contract is soft-deleted.
- Tool names are escaped in the tools summary, which fixes the XSS.
- The report has access rules, and it leaves out deleted contracts.

### Calendar, contacts, odometer

- The drop-off event uses the drop-off location.
- Changes are detected with a sha256 hash, which stays the same across restarts.
- Editing several contacts at once works.
- **Odometer:**
  - reading a contract no longer creates an odometer record;
  - setting the pickup km always saves it;
  - it no longer overwrites the vehicle's driver.

### Test runner (`a0a4b55`)

- `dev/run-tests`: a plain `make test` exited 1 even when every test passed. It now returns Odoo's exit code.
- `make test-check` was not affected.

### Cleanup

- **`models/car_rental_contract.py`** was rewritten, from 998 to 808 lines.
  - Field names and button names are the same, so the views, reports and mail templates are untouched.
  - Totals are now stored computed fields, instead of being written inside validation checks.
  - Side effects were moved out of the constraints and into `write()`.
- I removed dead code, the duplicate `unlink`, and the workarounds in the tests.
- `tests/KNOWN_BUGS.md` is now empty, but the `Bug:` convention is kept.

## Calls I made, to check

1. **Send contract:** Pickup/Dropoff users can also tick "Send a contract to client", because it's on their pickup form. It isn't in the spec's list.
2. **Calendar re-sync on contact changes:** it runs only when a name, phone or mobile changes, and only for contracts where the contact is the customer or the driver.
3. **Negative rent line:** on the final invoice, the rent line is still shown when it comes out negative. Odoo will then refuse to post the invoice, so the overpayment is visible instead of silently dropped.
4. **Re-pricing:** the price is recalculated whenever the dates change, whatever the contract's state.

## Before deploying

1. **Price bands:** cars without price bands, or with gaps in them, can no longer be confirmed.
2. **Calendar events:** the first sync after the upgrade rewrites each event once, because the way changes are detected has changed.
3. **Time zone:** set it to Europe/Lisbon on the company's contact, or on OdooBot. Otherwise the daily jobs use UTC.
4. **Contract numbers:** a new company's sequence copies the module's prefix and padding. Change it in Settings > Technical > Sequences if one company needs another prefix.
5. **Your `.env`:** remove `EXTRA_ADDONS_PATH` from it yourself.

## Open decisions

- **`test-suite` and `fix-pricing`:** merge them into `dev-environment` locally, push them and open a PR, or keep them as they are.
- **Second review:** whether to get an independent code review before merging.
