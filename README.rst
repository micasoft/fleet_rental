.. image:: https://img.shields.io/badge/license-AGPL--3-blue.svg
    :target: https://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3

Fleet Rental Management
=======================
This module will helps you to give the vehicles for Rent.

The intention of this fork is to evolve the existing addon to a different set of features.

- Pick up and Drop off location [WIP]
- Calender view [WIP]

Local development
=================
Runs this addon on Odoo 18 in Docker, against an external PostgreSQL server
on the LAN. Nothing here touches any other Odoo stack or database.

Prerequisites
-------------
- Docker with Compose v2, and ``make``.
- A database created by you on the LAN Postgres server: UTF8, owned by the
  role Odoo will use. Only ``make restore`` drops/recreates it (that one
  database, after confirmation).
- ``pg_hba.conf`` on that server allows this machine for that role/database.

Setup
-----
1. ``cp .env.example .env`` and set ``PG_HOST``, ``PG_PORT``, ``PG_USER``,
   ``PG_DATABASE``.
2. Write the password (never in ``.env``)::

     mkdir -p .secrets && printf '%s' 'PASSWORD' > .secrets/pg_password && chmod 600 .secrets/pg_password

   ``.env`` and ``.secrets/`` are gitignored. The password is passed as a
   Docker secret and exported as ``PGPASSWORD`` inside the container, so it
   does not appear in ``docker inspect`` or process arguments.
3. ``make psql-check`` — must print your user and database.
4. Load data, one of:

   - restore a backup (gzipped plain SQL, e.g. ``pg_dump -U postgres DB | gzip``)::

       make restore FILE=path/to/dump.sql.gz
       make restore-filestore FILE=path/to/backup-folder   # optional: attachments
       make update

   - empty database: ``make init`` (installs ``fleet_rental``, no demo data)

5. ``make up`` and open http://127.0.0.1:8369

Commands
--------
============================  ================================================================
``make up``                   run Odoo in the foreground (log in the terminal; Ctrl-C stops it)
``make down``                 stop Odoo
``make logs``                 follow the Odoo log
``make init``                 install ``fleet_rental`` into an empty database
``make update``               apply code changes to the database (``-u fleet_rental``);
                              stops Odoo if it was running
``make shell``                Odoo shell on the database
``make restore``              ``FILE=dump.sql.gz``: replace ``PG_DATABASE`` with the dump
``make restore-filestore``    ``FILE=folder|manifest.txt|tar.gz``: replace the dev filestore
``make test``                 run the tests on a throwaway database (see below)
``make version``              print the module version
``make package``              build the module zip (see Releases)
``make release``              cut a release on ``master`` (see Releases)
============================  ================================================================

Restoring a backup
------------------
``make restore FILE=...`` is interactive and must be run from a terminal
(Odoo must be stopped: ``make down``). It asks you to type the database name
to confirm, then the password of ``PG_ADMIN_USER`` (default ``postgres``);
that password is never stored.

Before anything is dropped, the file is checked: valid gzip, plain-SQL
``pg_dump`` (custom/tar formats are refused), complete (has the
``dump complete`` trailer), and no statements that act outside one database
(``\connect``, ``\!``, ``CREATE/DROP/ALTER DATABASE|ROLE|USER`` — i.e. dumps
made with ``pg_dump -C`` or ``pg_dumpall`` are refused). Then:

1. checks that ``PG_USER`` exists, then drops ``PG_DATABASE`` (only that name;
   system databases are refused) and recreates it as UTF8, owned by
   ``PG_USER``. The admin login is used for nothing else;
2. imports the dump **as** ``PG_USER`` in a single transaction, skipping
   ``OWNER TO``/``GRANT``/``REVOKE`` lines that reference production roles
   (outside table data). Every object is owned by ``PG_USER``; if the import
   fails, the database is left empty rather than half-imported;
3. runs ``odoo neutralize``: scheduled actions and outgoing mail servers are
   disabled so the copy never emails real customers. Only Odoo's internal
   auto-vacuum job stays active.

A SQL dump has no filestore: restore it with ``make restore-filestore``.
Run ``make update`` afterwards so the database matches this repo's code.

Restoring the filestore
-----------------------
``make restore-filestore FILE=...`` takes an ``odoo-data`` backup of
production's ``/var/lib/odoo``: the backup folder, its ``manifest.txt``, or
the ``.tar.gz`` itself. It is interactive (type the database name to
confirm) and Odoo must be stopped.

- Only ``filestore/<name>/`` is extracted; ``sessions/`` (production login
  sessions) and anything else in the archive are ignored.
- ``<name>`` is detected from the archive (e.g. ``prod``); if the archive
  holds several, choose with ``SOURCE_DB=name``.
- It replaces ``filestore/<PG_DATABASE>`` in the local Docker volume. Nothing
  on the Postgres server changes.
- If the database is reachable, it reports how many attachments the database
  references that are missing from the filestore (a dump and filestore from
  different dates).

Code changes
------------
The repo is mounted read-only at ``/mnt/extra-addons/fleet_rental``.
Odoo runs with ``--dev=reload,xml``: Python changes restart the server
automatically and XML views reload on browser refresh. New fields, data
files and security changes still need ``make update``.

Running the tests
-----------------
``make test`` installs ``fleet_rental`` into a throwaway PostgreSQL that
lives in RAM only for the run (``docker-compose.test.yml``) and runs the
addon's tests (``tests/``). It never uses ``.env``, the LAN server or your
database, and it removes its containers afterwards, also on failure or
Ctrl-C. A full run takes a few minutes.

- ``make test TAGS=/fleet_rental:TestPricing`` runs one test class
  (any Odoo ``--test-tags`` value).
- ``make test KEEP=1`` keeps the test database; the next ``KEEP=1`` run
  updates instead of reinstalling (much faster while writing tests). A run
  without ``KEEP`` always starts from scratch. Remove a kept database with
  ``docker compose -p fleet_rental_test -f docker-compose.test.yml down -v``.
- ``make test-check`` (also takes ``TAGS``/``KEEP``) passes only when the
  failing tests are exactly the known bugs: it lists any *unexpected
  failure* (a regression) and any known bug that *now passes* (fixed:
  remove its ``Bug:`` line and its row in ``tests/KNOWN_BUGS.md``).

The tests describe how the addon **should** behave, and all of them pass.
A test whose docstring starts with ``Bug:`` pins a known bug: it fails on
purpose until the bug is fixed, and is listed in ``tests/KNOWN_BUGS.md``.

Releases
--------
The version in ``__manifest__.py`` is the release: the git tag is
``v<version>`` and the zip ``fleet_rental-<version>.zip``. It follows
Odoo's convention ``18.0.x.y.z``: the Odoo series, then *major* (breaking
changes that need a migration), *minor* (compatible features) and *patch*
(fixes). The first release is ``18.0.2.0.0``. A new Odoo version is a new
branch, not a bump.

- ``make release`` (on ``master``, no uncommitted changes) runs
  ``make test-check``, bumps the version (``BUMP=patch`` by default, or
  ``minor``/``major``), commits ``Release <version>`` and tags it. The first
  release, with no tag yet, keeps the manifest's version. Then it pushes
  ``master`` and the tag together, which publishes the release on GitHub.
  ``master`` must match ``origin/master`` first. ``NO_PUSH=1`` keeps the
  commit and tag local (``git push --atomic origin master v<version>``
  publishes them later).
- ``make package`` builds ``dist/fleet_rental-<version>.zip`` from ``HEAD``
  (or ``REF=v18.0.2.0.0``): one ``fleet_rental/`` folder, without the dev
  tooling (``.gitattributes``). Only committed code goes in.

GitHub Actions (``.github/workflows/ci.yml``) run on every push and pull
request to ``master``: they build the zip, run the test suite on its
unzipped contents and keep it as a workflow artifact. A pushed tag must
match the manifest version, and its zip is attached to a GitHub release.

To install the zip, unzip it into a folder of the server's addons path,
then *Apps > Update Apps List* and install or upgrade *Fleet Rental
Management*. *Apps > Import Module* does not work for this addon: it
loads only data files (XML, CSV, static assets), not Python models.

Options (``.env``)
------------------
- ``ODOO_PORT`` (default ``8369``)
- ``ODOO_BIND`` (default ``127.0.0.1``; ``0.0.0.0`` exposes Odoo to the LAN)
- ``PGCONNECT_TIMEOUT`` (default ``10`` seconds)
- ``PG_ADMIN_USER`` (default ``postgres``), used only by ``make restore``
- ``EXTRA_ADDONS_PATH``: a host folder with other addons the database needs
  (e.g. a production copy uses ``muk_web_*``). Mounted read-only and added to
  the addons path *after* this repo, so this repo's ``fleet_rental`` always
  wins over another copy. Restart (``make down && make up``) after changing it.

Odoo runs with ``workers = 1``; see ``dev/odoo.conf``. With a single worker
Odoo cannot render PDF reports (wkhtmltopdf calls back into the server);
set ``workers = 2`` to print contracts/reservations. Odoo is pinned to
``PG_DATABASE`` and the database manager/list is disabled.
