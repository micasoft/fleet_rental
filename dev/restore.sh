#!/bin/bash
# Container side of `make restore`. Invoked as the entrypoint's `restore`
# subcommand (connection env already validated, PGPASSWORD = PG_USER's).
#
# stdin: first line = admin (superuser) password, rest = plain SQL dump
# (already validated by dev/restore-db on the host).
#
# The admin login is used ONLY to check the role and to drop/recreate
# $PG_DATABASE. The dump itself is imported as $PG_USER (the new database's
# owner) in a single transaction, so it cannot touch other databases or roles,
# every object ends up owned by $PG_USER, and a failure leaves no partial data.
set -euo pipefail

ADMIN_USER="${PG_ADMIN_USER:-postgres}"
IFS= read -r ADMIN_PASSWORD

ident='^[A-Za-z_][A-Za-z0-9_]*$'
for name in "$PG_DATABASE" "$PG_USER" "$ADMIN_USER"; do
    [[ "$name" =~ $ident ]] || { echo "refusing: '$name' is not a plain identifier" >&2; exit 1; }
done
case "$PG_DATABASE" in
    postgres|template0|template1) echo "refusing to drop system database $PG_DATABASE" >&2; exit 1 ;;
esac

admin() {
    PGPASSWORD="$ADMIN_PASSWORD" psql -X -w -q -v ON_ERROR_STOP=1 \
        -h "$PG_HOST" -p "$PG_PORT" -U "$ADMIN_USER" -d postgres "$@"
}
as_user() {
    psql -X -w -q -v ON_ERROR_STOP=1 \
        -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" "$@"
}

echo ">> target: database $PG_DATABASE on $PG_HOST:$PG_PORT, owner $PG_USER (admin $ADMIN_USER)" >&2
role_ok=$(admin -At -c "SELECT count(*) FROM pg_roles WHERE rolname = '$PG_USER' AND rolcanlogin;")
[ "$role_ok" = "1" ] || { echo "role $PG_USER does not exist or cannot log in; nothing was dropped" >&2; exit 1; }

echo ">> dropping and recreating $PG_DATABASE (owner $PG_USER)" >&2
admin -c "DROP DATABASE IF EXISTS \"$PG_DATABASE\" WITH (FORCE);"
admin -c "CREATE DATABASE \"$PG_DATABASE\" OWNER \"$PG_USER\" ENCODING 'UTF8' TEMPLATE template0;"

echo ">> importing dump as $PG_USER (single transaction)" >&2
# Outside COPY data blocks, drop statements that reference production roles or
# need superuser; ownership is implicit (PG_USER creates everything).
awk '
    in_copy { print; if ($0 == "\\.") in_copy = 0; next }
    /^COPY .* FROM stdin;$/ { in_copy = 1; print; next }
    /^ALTER [A-Z ]+ .+ OWNER TO [^;]+;$/ { next }
    /^ALTER DEFAULT PRIVILEGES / { next }
    /^(GRANT|REVOKE) .+;$/ { next }
    /^COMMENT ON EXTENSION / { next }
    /^SET transaction_timeout = / { next }
    { print }
' | as_user --single-transaction

not_owned=$(as_user -At -c "
    SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','S','f')
      AND pg_get_userbyid(c.relowner) <> current_user;")
[ "$not_owned" = "0" ] || { echo "error: $not_owned relations are not owned by $PG_USER" >&2; exit 1; }

echo ">> neutralizing (crons, mail servers off)" >&2
odoo neutralize --db_host "$PG_HOST" --db_port "$PG_PORT" --db_user "$PG_USER" -d "$PG_DATABASE"

echo ">> done. Next: make update && make up" >&2
