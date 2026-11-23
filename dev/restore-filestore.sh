#!/bin/bash
# Container side of `make restore-filestore`. Invoked as the entrypoint's
# `restore-filestore SOURCE_DB` subcommand, as the odoo user.
# stdin: the odoo-data .tar.gz. Extracts only filestore/SOURCE_DB/ into
# /var/lib/odoo/filestore/$PG_DATABASE (replacing it). Sessions and anything
# else in the archive are ignored.
set -euo pipefail
src="$1"
[[ "$src" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "bad source name: $src" >&2; exit 1; }
[[ "$PG_DATABASE" =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "bad PG_DATABASE: $PG_DATABASE" >&2; exit 1; }

base=/var/lib/odoo/filestore
target="$base/$PG_DATABASE"
tmp="/var/lib/odoo/.restore-filestore.$$"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$base" "$tmp"

echo ">> extracting filestore/$src -> filestore/$PG_DATABASE" >&2
tar -xz -C "$tmp" --no-same-owner --no-same-permissions \
    --wildcards "filestore/$src/*" "./filestore/$src/*" 2>/dev/null || true
if [ -d "$tmp/filestore/$src" ]; then
    extracted="$tmp/filestore/$src"
else
    echo "nothing extracted for filestore/$src" >&2
    exit 1
fi
count=$(find "$extracted" -type f | wc -l)
[ "$count" -gt 0 ] || { echo "filestore/$src is empty in the archive" >&2; exit 1; }

rm -rf "$target"
mv "$extracted" "$target"
echo ">> $count files in $target" >&2

# Compare with the database, if reachable.
if refs=$(psql -X -w -At -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" \
        -c "SELECT DISTINCT store_fname FROM ir_attachment WHERE store_fname IS NOT NULL" 2>/dev/null); then
    total=0; missing=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        total=$((total + 1))
        [ -f "$target/$f" ] || missing=$((missing + 1))
    done <<< "$refs"
    echo ">> database references $total files, $missing missing from the filestore" >&2
    [ "$missing" -eq 0 ] || echo "   (dump and filestore are probably from different dates)" >&2
else
    echo ">> database not reachable/restored: skipped the attachment check" >&2
fi
echo ">> done" >&2
