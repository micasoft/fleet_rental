# Local dev stack for fleet_rental. See README.rst "Local development".
COMPOSE ?= docker compose
MODULE  := fleet_rental
# Long-running server container only (excludes one-off `compose run` containers).
SERVER_ID = docker ps -q --filter label=com.docker.compose.project=fleet_rental_dev \
	--filter label=com.docker.compose.service=odoo --filter label=com.docker.compose.oneoff=False

.PHONY: help check-env psql-check up down logs init update shell restore restore-filestore test test-check version package release

help:
	@echo "check-env   verify .env and .secrets/pg_password exist"
	@echo "psql-check  test the database connection and credentials"
	@echo "up          run Odoo in the foreground, Ctrl-C stops it (http://127.0.0.1:8369)"
	@echo "down        stop Odoo"
	@echo "logs        follow Odoo logs"
	@echo "init        install $(MODULE) into an empty database"
	@echo "update      update $(MODULE) to the code in this repo (stops Odoo if running)"
	@echo "shell       open an Odoo shell on the database"
	@echo "restore     FILE=dump.sql.gz: drop PG_DATABASE, import the dump, set owner, neutralize"
	@echo "restore-filestore  FILE=backup-folder|manifest.txt|odoo-data.tar.gz [SOURCE_DB=name]"
	@echo "test        run the tests on a throwaway database [TAGS=/fleet_rental:TestX] [KEEP=1]"
	@echo "test-check  like test, but passes only if the failures are exactly the known bugs (Bug: tests)"
	@echo "version     print the module version (__manifest__.py)"
	@echo "package     build dist/$(MODULE)-<version>.zip from committed code [REF=HEAD]"
	@echo "release     on master: test, bump, commit, tag and push v<version> [BUMP=patch|minor|major] [SKIP_TESTS=1] [NO_PUSH=1]"

check-env:
	@test -f .env || { echo "missing .env: copy .env.example to .env and fill it in" >&2; exit 1; }
	@test -s .secrets/pg_password || { echo "missing or empty .secrets/pg_password: see .env.example" >&2; exit 1; }

psql-check: check-env
	$(COMPOSE) run --rm odoo psql -c "select current_user, current_database(), version();"

up: check-env
	$(COMPOSE) up

down: check-env
	$(COMPOSE) down

logs: check-env
	$(COMPOSE) logs -f odoo

init: check-env
	$(COMPOSE) run --rm odoo -i $(MODULE) --stop-after-init

update: check-env
	@running=$$($(SERVER_ID)); \
	if [ -n "$$running" ]; then $(COMPOSE) stop odoo; fi; \
	$(COMPOSE) run --rm odoo -u $(MODULE) --stop-after-init; rc=$$?; \
	if [ -n "$$running" ]; then echo "Odoo was stopped for the update: run make up again"; fi; \
	exit $$rc

shell: check-env
	$(COMPOSE) run --rm odoo shell

restore: check-env
	@./dev/restore-db

restore-filestore: check-env
	@./dev/restore-filestore

# Does not need .env: runs on its own throwaway Postgres.
test:
	@TAGS='$(TAGS)' KEEP='$(KEEP)' ./dev/run-tests

test-check:
	@TAGS='$(TAGS)' KEEP='$(KEEP)' CHECK=1 ./dev/run-tests

# Releases (README.rst "Releases").
version:
	@./dev/version

package:
	@REF='$(or $(REF),HEAD)' ./dev/package

release:
	@BUMP='$(or $(BUMP),patch)' SKIP_TESTS='$(SKIP_TESTS)' NO_PUSH='$(NO_PUSH)' ./dev/release
