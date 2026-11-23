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
  role Odoo will use. The stack never creates or drops databases.
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
       make update

   - empty database: ``make init`` (installs ``fleet_rental``, no demo data)

5. ``make up`` and open http://127.0.0.1:8369

Commands
--------
==================  ==============================================================
``make up``         start Odoo in the background
``make down``       stop Odoo
``make logs``       follow the Odoo log
``make init``       install ``fleet_rental`` into an empty database
``make update``     apply code changes to the database (``-u fleet_rental``);
                    restarts Odoo if it was running
``make shell``      Odoo shell on the database
``make restore``    ``FILE=dump.sql.gz``: replace ``PG_DATABASE`` with the dump
                    (see below)
==================  ==============================================================

Restoring a backup
------------------
``make restore FILE=...`` is interactive and must be run from a terminal
(Odoo must be stopped: ``make down``). It asks you to type the database name
to confirm, then the password of ``PG_ADMIN_USER`` (default ``postgres``);
that password is never stored. It then:

1. drops ``PG_DATABASE`` (only that name; system databases are refused) and
   recreates it as UTF8, owned by ``PG_USER``;
2. imports the dump as the admin user, skipping ``OWNER TO``/``GRANT`` lines
   that reference production roles;
3. hands every table, sequence, view, function and the ``public`` schema to
   ``PG_USER``;
4. runs ``odoo neutralize``: scheduled actions and outgoing mail servers are
   disabled so the copy never emails real customers. Only Odoo's internal
   auto-vacuum job stays active.

A SQL dump has no filestore: attachments, generated PDFs and images from
production are missing in the copy. Run ``make update`` afterwards so the
database matches this repo's code.

Code changes
------------
The repo is mounted read-only at ``/mnt/extra-addons/fleet_rental``.
Odoo runs with ``--dev=reload,xml``: Python changes restart the server
automatically and XML views reload on browser refresh. New fields, data
files and security changes still need ``make update``.

Options (``.env``)
------------------
- ``ODOO_PORT`` (default ``8369``)
- ``ODOO_BIND`` (default ``127.0.0.1``; ``0.0.0.0`` exposes Odoo to the LAN)
- ``PGCONNECT_TIMEOUT`` (default ``10`` seconds)
- ``PG_ADMIN_USER`` (default ``postgres``), used only by ``make restore``

Odoo runs with ``workers = 1``; see ``dev/odoo.conf``. With a single worker
Odoo cannot render PDF reports (wkhtmltopdf calls back into the server);
set ``workers = 2`` to print contracts/reservations. Odoo is pinned to
``PG_DATABASE`` and the database manager/list is disabled.
