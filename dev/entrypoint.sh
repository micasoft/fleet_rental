#!/bin/bash
# Entrypoint for the local dev stack.
# Reads the connection from env (.env) and the password from a Docker secret,
# exports it as PGPASSWORD (read by libpq) so it never appears in process args,
# and pins Odoo to a single database.
# Starts as root only to read the secret (the host file can stay chmod 600),
# then drops to the image's unprivileged `odoo` user.
#
# Usage (container args):
#   <odoo args...>   run odoo
#   shell [args]     odoo shell
#   psql [args]      psql connected to $PG_DATABASE
#   restore          used by `make restore` (see dev/restore.sh)
#   restore-filestore SRC   used by `make restore-filestore` (see dev/restore-filestore.sh)
set -euo pipefail

SECRET_FILE=/run/secrets/pg_password

for var in PG_HOST PG_PORT PG_USER PG_DATABASE; do
    if [ -z "${!var:-}" ]; then
        echo "missing ${var} in .env" >&2
        exit 1
    fi
done

if [ ! -s "$SECRET_FILE" ]; then
    echo "missing or empty ${SECRET_FILE} (write the password to .secrets/pg_password)" >&2
    exit 1
fi
# $(< file) strips trailing newlines; also drop CR (file saved with CRLF).
PGPASSWORD="$(< "$SECRET_FILE")"
PGPASSWORD="${PGPASSWORD//$'\r'/}"
if [ -z "${PGPASSWORD//[[:space:]]/}" ]; then
    echo "${SECRET_FILE} contains only whitespace" >&2
    exit 1
fi
export PGPASSWORD
# Fail fast on an unreachable host instead of hanging (libpq, also used by Odoo).
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"

# Drop privileges for everything we exec.
RUN=()
if [ "$(id -u)" = "0" ]; then
    RUN=(setpriv --reuid=odoo --regid=odoo --init-groups)
    export HOME=/var/lib/odoo
fi

# Extra addons (EXTRA_ADDONS_PATH): appended after this repo, so the repo's
# fleet_rental always wins over another copy.
EXT=/mnt/extra-addons-ext
ADDONS_ARGS=()
if compgen -G "$EXT/*/__manifest__.py" >/dev/null; then
    ADDONS_ARGS=(--addons-path "/usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons,$EXT")
    if [ -e "$EXT/fleet_rental" ]; then
        echo "warning: EXTRA_ADDONS_PATH also has fleet_rental; ignored, this repo's copy is used" >&2
    fi
fi

DB_ARGS=(
    --db_host "$PG_HOST"
    --db_port "$PG_PORT"
    --db_user "$PG_USER"
    -d "$PG_DATABASE"
    --db-filter "^${PG_DATABASE}\$"
)

case "${1:-}" in
    psql)
        shift
        exec env LC_ALL=C.UTF-8 "${RUN[@]}" psql -w -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" "$@"
        ;;
    restore)
        exec env LC_ALL=C.UTF-8 "${RUN[@]}" /dev-restore.sh
        ;;
    restore-filestore)
        shift
        exec env LC_ALL=C.UTF-8 "${RUN[@]}" /dev-restore-filestore.sh "$@"
        ;;
    shell)
        shift
        exec "${RUN[@]}" odoo shell "${ADDONS_ARGS[@]}" "${DB_ARGS[@]}" "$@"
        ;;
    *)
        exec "${RUN[@]}" odoo "${ADDONS_ARGS[@]}" "${DB_ARGS[@]}" "$@"
        ;;
esac
