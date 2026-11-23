#!/bin/bash
# Container side of `make restore`. Invoked as the entrypoint's `restore`
# subcommand (connection env already validated, PGPASSWORD = PG_USER's).
#
# stdin: first line = admin (superuser) password, rest = plain SQL dump.
# Drops and recreates $PG_DATABASE owned by $PG_USER, imports the dump as
# $PG_ADMIN_USER, hands every object to $PG_USER, then neutralizes the copy.
set -euo pipefail

ADMIN_USER="${PG_ADMIN_USER:-postgres}"
USER_PASSWORD="$PGPASSWORD"
IFS= read -r ADMIN_PASSWORD

ident='^[A-Za-z_][A-Za-z0-9_]*$'
for name in "$PG_DATABASE" "$PG_USER" "$ADMIN_USER"; do
    [[ "$name" =~ $ident ]] || { echo "refusing: '$name' is not a plain identifier" >&2; exit 1; }
done
case "$PG_DATABASE" in
    postgres|template0|template1) echo "refusing to drop system database $PG_DATABASE" >&2; exit 1 ;;
esac

admin() {
    PGPASSWORD="$ADMIN_PASSWORD" psql -X -q -v ON_ERROR_STOP=1 \
        -h "$PG_HOST" -p "$PG_PORT" -U "$ADMIN_USER" "$@"
}

echo ">> dropping and recreating $PG_DATABASE (owner $PG_USER)" >&2
admin -d postgres -c "DROP DATABASE IF EXISTS \"$PG_DATABASE\" WITH (FORCE);"
admin -d postgres -c "CREATE DATABASE \"$PG_DATABASE\" OWNER \"$PG_USER\" ENCODING 'UTF8' TEMPLATE template0;"

echo ">> importing dump" >&2
# Drop ownership/privilege lines that reference production roles, and a PG17+
# setting older servers reject. Ownership is fixed below.
sed -E \
    -e '/^ALTER [A-Z ]+ .+ OWNER TO [^;]+;$/d' \
    -e '/^(GRANT|REVOKE) .+;$/d' \
    -e '/^SET transaction_timeout = /d' \
  | admin -d "$PG_DATABASE"

echo ">> handing all objects to $PG_USER" >&2
admin -d "$PG_DATABASE" -v owner="$PG_USER" <<'SQL'
SELECT set_config('restore.owner', :'owner', false);
DO $$
DECLARE
    o text := current_setting('restore.owner');
    r record;
BEGIN
    EXECUTE format('ALTER SCHEMA public OWNER TO %I', o);
    FOR r IN SELECT c.oid::regclass AS obj, c.relkind FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f','S')
    LOOP
        BEGIN
            EXECUTE format('ALTER %s %s OWNER TO %I',
                CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                               WHEN 'f' THEN 'FOREIGN TABLE' WHEN 'S' THEN 'SEQUENCE'
                               ELSE 'TABLE' END, r.obj, o);
        EXCEPTION WHEN others THEN
            -- sequences owned by a column follow their table
            NULL;
        END;
    END LOOP;
    FOR r IN SELECT p.oid::regprocedure AS obj, p.prokind FROM pg_proc p
             JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'public'
               AND NOT EXISTS (SELECT 1 FROM pg_depend d
                               WHERE d.objid = p.oid AND d.deptype = 'e')
    LOOP
        EXECUTE format('ALTER %s %s OWNER TO %I',
            CASE r.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'a' THEN 'AGGREGATE' ELSE 'FUNCTION' END,
            r.obj, o);
    END LOOP;
    FOR r IN SELECT t.oid::regtype AS obj FROM pg_type t
             JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = 'public' AND t.typtype IN ('c','d','e')
               AND (t.typrelid = 0 OR (SELECT relkind FROM pg_class WHERE oid = t.typrelid) = 'c')
               AND NOT EXISTS (SELECT 1 FROM pg_depend d
                               WHERE d.objid = t.oid AND d.deptype = 'e')
    LOOP
        EXECUTE format('ALTER TYPE %s OWNER TO %I', r.obj, o);
    END LOOP;
END $$;
SQL

remaining=$(admin -d "$PG_DATABASE" -At -c "
    SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m')
      AND pg_get_userbyid(c.relowner) <> '$PG_USER';")
if [ "$remaining" != "0" ]; then
    echo "error: $remaining tables/views are not owned by $PG_USER" >&2
    exit 1
fi

echo ">> neutralizing (crons, mail servers off)" >&2
PGPASSWORD="$USER_PASSWORD" odoo neutralize \
    --db_host "$PG_HOST" --db_port "$PG_PORT" --db_user "$PG_USER" -d "$PG_DATABASE"

echo ">> done. Next: make update && make up" >&2
