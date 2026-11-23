# Local dev environment for fleet_rental — design

## Intent
Run the `fleet_rental` addon on this machine against Odoo 18 so it can be
explored, then used as the base for tests and future changes. No code or
business-logic changes in this step.

## Goals
- One command brings up Odoo 18 with this repo mounted as an addon.
- Python/XML edits are picked up with a restart or module update, no image rebuild.
- Connection to an external Postgres on the LAN, defined cleanly and without
  secrets in git or in the chat.
- Low local footprint: no local Postgres container.

## Non-goals
- Automated tests, CI, linting (next step, will reuse this stack).
- Fixing bugs or refactoring the addon.
- Restoring production data.
- IDE debugger attach (can be added later).

## Anti-goals
- Touching any other Odoo stack on the host, its Postgres, volumes or databases.
- Password in git, `.env`, `docker inspect` or chat.
- Odoo able to reach any database other than the one created for it.

## Constraints
- Postgres is on the LAN, no SSL for now. The user creates the database
  (UTF8, owned by the dev role); the role is not expected to have CREATEDB.
- pg_hba on that server must allow this machine's IP for that role/DB.
- Limited resources on this machine.

## Approaches
- **A. Dev Docker stack inside this repo** — chosen. Isolated from the
  production stack, same `odoo:18` image as production, reusable later for tests.
- B. Extra service in the existing production compose file — rejected: shares the
  Postgres that holds production data.
- C. Native Odoo source + venv — rejected: more host setup (wkhtmltopdf, deps),
  drifts from the production image.
- Variation chosen by the user: external LAN Postgres instead of a local container.

## Design
Files added to the repo:

| File | Committed | Purpose |
|---|---|---|
| `docker-compose.yml` | yes | Single `odoo` service, `odoo:18` image, port `8369:8069` |
| `dev/odoo.conf` | yes | Odoo config: addons path, `list_db = False`, `workers = 1` |
| `.env.example` | yes | Documents `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_DATABASE` |
| `.env` | no (gitignored) | Real values for the above |
| `.secrets/pg_password` | no (gitignored) | Password only; the user writes it themselves |
| `Makefile` | yes | `up`, `down`, `logs`, `init`, `update`, `shell`, `psql-check` |
| `README.rst` section | yes | How to set up and run |

Connection:
- `HOST`, `PORT`, `USER` env vars come from `.env`; password via Docker secret
  mounted at `/run/secrets/pg_password` and `PASSWORD_FILE` (supported by the
  official image entrypoint).
- Odoo is pinned to one DB: `-d $PG_DATABASE --db-filter=^$PG_DATABASE$`,
  `list_db = False`.
- `db_sslmode` left at default (`prefer`); switch to `require` when SSL is added.

Runtime:
- Repo mounted at `/mnt/extra-addons/fleet_rental`; named volume for
  `/var/lib/odoo` (filestore/sessions).
- `workers = 1` (prefork: one HTTP worker plus cron and gevent processes),
  with conservative `limit_memory_*` values; `--dev=xml` so view changes reload on refresh;
  Python changes need `make update` / restart (auto-reload needs watchdog,
  which the image may lack — builder to check).
- No demo data (`--without-demo=all`). The user provides the data.
  - If the provided data is a DB that already has `fleet_rental` installed:
    `make update` (`-u fleet_rental --stop-after-init`) brings it to the repo code.
  - If the DB is empty: `make init` (`-i fleet_rental --stop-after-init`).

## Left to the builder
- Exact `Makefile` recipes and entrypoint arg passing.
- Whether `odoo:18` has watchdog; if so enable `--dev=reload,xml`.
- Pinning the image (tag vs digest) — default `odoo:18.0`.
- A `psql-check` target that verifies connectivity/credentials before `init`.

## Addendum (2026-11-23): `make restore`
Requested by the user after approval; supersedes "the stack never creates or
drops databases" for `PG_DATABASE` only.
- `make restore FILE=dump.sql.gz` (gzipped plain SQL, as produced by
  `pg_dump -U postgres DB | gzip`).
- Interactive only: confirm by typing the DB name; admin (`PG_ADMIN_USER`,
  default `postgres`) password prompted, never stored.
- Validate the dump first (gzip, plain format, complete, no
  `\connect`/`\!`/database- or role-level statements).
- Admin used only to check the role and drop + recreate `PG_DATABASE` owned by
  `PG_USER`; the dump is imported as `PG_USER` in a single transaction,
  skipping production owner/grant lines.
- Always `odoo neutralize` the copy.
- Refuses while Odoo is running, and refuses system databases.

## Addendum (2026-11-23): `make restore-filestore`
- `make restore-filestore FILE=<backup folder | manifest.txt | odoo-data.tar.gz> [SOURCE_DB=name]`.
- Extracts only `filestore/<source>/` (never `sessions/`) into
  `filestore/$PG_DATABASE` on the local Docker volume, replacing it.
- Interactive confirmation; Odoo must be stopped. Reports attachments the DB
  references that are missing from the filestore.
