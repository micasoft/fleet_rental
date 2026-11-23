# Local Dev Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the `fleet_rental` addon locally on Odoo 18 in Docker, connected to an external LAN Postgres database, with no secrets in git.

**Architecture:** One `odoo` service in a repo-local `docker-compose.yml`, using the official `odoo:18` image with a small custom entrypoint (`dev/entrypoint.sh`) that reads the connection from `.env` and the password from a Docker secret, and pins Odoo to a single database. A `Makefile` wraps the day-to-day commands.

**Tech Stack:** Docker Compose v2, `odoo:18` (verified: Odoo 18.0-20261112, has `watchdog`, `wkhtmltopdf`, `psql`), GNU Make, Bash.

**Spec:** `docs/superpowers/specs/2026-11-23-local-dev-environment-design.md`

## Global Constraints

- Image: `odoo:18`. Host port: `8369` → container `8069`.
- Postgres is external on the LAN; no Postgres container in this stack. No SSL (`db_sslmode` default).
- The database is created by the user; the stack never creates or drops databases.
- Odoo pinned to one DB: `-d $PG_DATABASE`, `--db-filter=^$PG_DATABASE$`, `list_db = False`.
- `workers = 1`. No demo data (`without_demo = all`).
- Password only in `.secrets/pg_password` (gitignored, written by the user). Never in `.env`, git, compose output, container args, or chat.
- `.env` gitignored; `.env.example` committed with keys `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_DATABASE` (plus optional `ODOO_PORT`).
- Do not touch any other Odoo stack on the host, or its volumes/databases.
- No changes to addon Python/XML.

## Decisions made while planning (deviations from the spec)

- **Custom entrypoint instead of the image's `PASSWORD_FILE` support.** Verified in the image: its entrypoint passes the password as `--db_password <pw>` on the command line (visible in host `ps`), and `wait-for-psql.py` connects to the `postgres` database, which fails if `pg_hba` only allows the dev DB. `dev/entrypoint.sh` instead exports `PGPASSWORD` from the secret (libpq reads it; Odoo 18 only sends a password when `db_password` is set in config) and passes host/port/user as args.
- **Port bound to `127.0.0.1` by default** (`ODOO_BIND`, default `127.0.0.1`) since the dev instance's admin is reachable from it. Set `ODOO_BIND=0.0.0.0` in `.env` to open it to the LAN.

## Review Focus

1. Missing/empty `.secrets/pg_password` or a missing `.env` key → fail immediately with a message naming what is missing, before any connection attempt.
2. Wrong password / `pg_hba` rejection → `make psql-check` prints the Postgres error and exits non-zero.
3. Password leaking → not present in `docker compose config`, `docker inspect`, or host `ps` while Odoo runs.
4. Password file saved with a trailing newline (`echo pw > file`) → still works.
5. `make update` while the server is running → the module update runs and the server comes back up afterwards.

---

### Task 1: Compose stack and connection handling

**Files:**
- Create: `.gitignore`, `.env.example`, `docker-compose.yml`, `dev/odoo.conf`, `dev/entrypoint.sh` (executable)

**Interfaces:**
- Produces: service name `odoo`; entrypoint subcommands used by Task 2:
  - `<odoo args...>` → `exec odoo <db args> <args>`
  - `shell [args]` → `exec odoo shell <db args> [args]`
  - `psql [args]` → `exec psql` connected to `$PG_DATABASE` with `[args]`
  - where `<db args>` = `--db_host $PG_HOST --db_port $PG_PORT --db_user $PG_USER -d $PG_DATABASE --db-filter ^$PG_DATABASE$`
- Produces: env keys `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_DATABASE`, `ODOO_PORT` (default 8369), `ODOO_BIND` (default 127.0.0.1).

- [ ] **Step 1: `.gitignore`** with `.env`, `.secrets/`, `__pycache__/`, `*.pyc`. Verify:
  `mkdir -p .secrets && touch .env .secrets/pg_password && git check-ignore .env .secrets/pg_password` → prints both paths.

- [ ] **Step 2: `.env.example`** with the four `PG_*` keys (placeholder values, `PG_PORT=5432`), and commented `ODOO_PORT=8369`, `ODOO_BIND=127.0.0.1`, plus a comment pointing to `.secrets/pg_password`.

- [ ] **Step 3: `dev/odoo.conf`** — `[options]` with:
  `addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons`, `data_dir = /var/lib/odoo`, `list_db = False`, `without_demo = all`, `workers = 1`, `max_cron_threads = 1`, `limit_memory_soft = 671088640`, `limit_memory_hard = 805306368`, `limit_time_cpu = 600`, `limit_time_real = 1200`, `log_level = info`. No `db_*` keys.

- [ ] **Step 4: `dev/entrypoint.sh`** (`set -euo pipefail`):
  - fail with `missing <NAME> in .env` for each unset/empty `PG_*` key;
  - fail with `missing or empty /run/secrets/pg_password` if the secret is absent/empty;
  - `export PGPASSWORD="$(< /run/secrets/pg_password)"` (command substitution strips trailing newlines — Review Focus 4);
  - dispatch subcommands per the Interfaces block.

- [ ] **Step 5: `docker-compose.yml`** — service `odoo`: `image: odoo:18`, `entrypoint: ["/dev-entrypoint.sh"]`, `command: ["--dev=reload,xml"]`, `env_file: .env`, ports `"${ODOO_BIND:-127.0.0.1}:${ODOO_PORT:-8369}:8069"`, `mem_limit: 1g`, secret `pg_password` from `./.secrets/pg_password`, volumes: `.:/mnt/extra-addons/fleet_rental:ro`, `./dev/odoo.conf:/etc/odoo/odoo.conf:ro`, `./dev/entrypoint.sh:/dev-entrypoint.sh:ro`, named volume `fleet_rental_dev_data:/var/lib/odoo`. Top-level `name: fleet_rental_dev`.

- [ ] **Step 6: Verify config and failure messages** (with the empty `.env` / secret from Step 1):
  - `docker compose config >/dev/null` → exit 0.
  - `docker compose run --rm odoo --version` → exits non-zero with `missing PG_HOST in .env`.
  - Fill `.env` with dummy values (`PG_HOST=127.0.0.1` etc.), keep secret empty → `missing or empty /run/secrets/pg_password`.
  - Put `dummy` in the secret → `docker compose run --rm odoo --version` prints `Odoo Server 18.0-…`.
  - `docker compose config | grep -c dummy` → `0` (Review Focus 3).
  - Remove the dummy `.env` and secret afterwards (`rm .env .secrets/pg_password`).

- [ ] **Step 7: Commit**
  ```bash
  git add .gitignore .env.example docker-compose.yml dev/
  git commit -m "Add local dev Docker stack for Odoo 18 with external Postgres"
  ```

### Task 2: Makefile

**Files:**
- Create: `Makefile`

**Interfaces:**
- Consumes: service `odoo` and entrypoint subcommands from Task 1.
- Produces: targets `check-env`, `psql-check`, `up`, `down`, `logs`, `init`, `update`, `shell`.

- [ ] **Step 1: Write targets**
  - `check-env`: fails with a clear message if `.env` is missing or `.secrets/pg_password` is missing/empty. All other targets depend on it.
  - `psql-check`: `docker compose run --rm odoo psql -c "select current_user, current_database(), version();"`
  - `up` / `down` / `logs`: `docker compose up -d` / `down` / `logs -f odoo`.
  - `init`: `docker compose run --rm odoo -i fleet_rental --stop-after-init`
  - `update`: stop `odoo` if running, `docker compose run --rm odoo -u fleet_rental --stop-after-init`, then start it again if it had been running (Review Focus 5).
  - `shell`: `docker compose run --rm odoo shell`
  - `.PHONY` for all.

- [ ] **Step 2: Verify the checks without a database**
  - With no `.env`: `make psql-check` → fails with the `check-env` message, no container started.
  - `.env` with `PG_HOST` set to an unused LAN IP and secret `dummy`: `make psql-check` → non-zero exit and a `psql: error: connection to server …` message (Review Focus 2). Clean up afterwards.

- [ ] **Step 3: Commit**
  ```bash
  git add Makefile
  git commit -m "Add Makefile for the local dev stack"
  ```

### Task 3: Bring-up against the real database and README

**Files:**
- Modify: `README.rst` (append a "Local development" section)

**Interfaces:**
- Consumes: all `make` targets from Task 2.

- [ ] **Step 1: User checkpoint** — ask the user to fill `.env` from `.env.example` and write the password themselves:
  `! mkdir -p .secrets && printf '%s' 'PASSWORD' > .secrets/pg_password && chmod 600 .secrets/pg_password`
  and confirm the DB exists (UTF8, owned by the role) and `pg_hba` allows this host. Do not read or print the secret.

- [ ] **Step 2: `make psql-check`** → one row with the expected user and database.

- [ ] **Step 3: Load the module** — ask the user whether their DB already has `fleet_rental` installed (their provided data) or is empty; run `make update` or `make init` accordingly. Expected: exits 0; log has no `ERROR`/`CRITICAL` lines (warnings are recorded for later, not fixed).

- [ ] **Step 4: Run and probe**
  - `make up`, then `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8369/web/login` → `200`.
  - `curl -s http://127.0.0.1:8369/web/database/selector` → not a DB list (list_db off).
  - `ps aux | grep -c '[d]b_password'` → `0`, and `docker inspect fleet_rental_dev-odoo-1 | grep -ci pgpassword` → `0` (Review Focus 3).
  - Check `--dev=reload` actually reloads: touch `models/__init__.py`, the log shows a reload. If it doesn't work with `workers = 1`, change the command to `--dev=xml` and note it in the README.
  - Ask the user to log in at http://127.0.0.1:8369 and open Car Rental.

- [ ] **Step 5: README "Local development" section** — prerequisites (Docker, LAN DB created by the user, `pg_hba`), the setup steps from Step 1, the target list with one line each, when to use `init` vs `update`, how Python/XML changes are picked up, `ODOO_BIND` / `ODOO_PORT`.

- [ ] **Step 6: Commit**
  ```bash
  git add README.rst
  git commit -m "Document the local dev environment"
  ```
