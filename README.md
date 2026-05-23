# pgh-ticket

scanner for the **Pittsburgh Parking Authority** ticket portal. probes ticket numbers, scrapes details, stores results in postgresql.

## the problem

the parking authority portal (`dsparkingportal.com/pittsburgh`) only lets you look up one ticket number at a time. there's no list-all, no search-by-date, no bulk export. ticket numbers are 7 digits in range **2,078,060–9,262,307** (~7.18M possibilities). valid tickets cluster in blocks of 10-100+, separated by voids of nothing.

this tool brute-forces through the space intelligently — probes at intervals to find clusters, then deep-scans around hits.

## commands

```
pgh-ticket lookup 9244895
pgh-ticket lookup 8950000-8950005 --verbose
```

one-off lookups. hits the api, stores in db. useful for testing connectivity.

```
pgh-ticket scan 8950000-9245300 --until 2026-05-13 -w 20 --step 100
```

**two-phase scan.** phase 1 probes every `--step` numbers (~3k requests for a 295k range). phase 2 deep-scans merged windows around every hit, fetching details for each ticket. this is the main collection command.

```
pgh-ticket sync 2026-05-08 --step 200 -w 3
```

probe-only, date-filtered. finds tickets for one specific date. no deep scan — just search results filtered by issue date. circuit breaker built in (sleeps on repeated errors).

```
pgh-ticket list --state PA --status Open -n 20
pgh-ticket list --date-from 2026-05-01 --date-to 2026-05-08 --verbose
pgh-ticket list --state PA --limit 5 --json
pgh-ticket stats
pgh-ticket stats --json
```

read-only queries. `list` filters by state, status, date range. `stats` shows aggregate breakdowns and recent scan history. add `--json` for machine-readable output.

```
pgh-ticket backfill details -w 40 --proxy socks5://10.64.0.1:1080
pgh-ticket backfill details -w 40 --dry-run
pgh-ticket backfill keys -w 10 --limit 1000
pgh-ticket backfill geocode -w 5
pgh-ticket backfill geocode -w 5 --dry-run
```

enrich stored tickets. `details` fetches officer/location/violation for tickets missing them. `keys` fetches the api's internal ticket key. `geocode` turns location strings into lat/lon via mapbox. `--dry-run` shows what would be done without writing to db.

```
pgh-ticket errors list
pgh-ticket errors stats
pgh-ticket errors clear
pgh-ticket errors retry -w 5
```

manage failed lookups. `retry` re-attempts unresolved errors.

## ticket numbering quirks

- **dates are not monotonic.** 9245000 might be may 1, 9245300 might be april 21. different blocks assigned at different times.
- **no modulo pattern.** unlike some cities (sf's add-11 rule), pgh tickets cluster unpredictably. only reliable method: probe + deep-scan.
- **upper bound:** ~9,262,307. lower bound: ~2,078,060.
- **72-hour lag.** recently issued tickets may not appear for up to 3 days.

## database

postgresql via sqlalchemy 2.0 async. connection defaults:

| var | default |
|---|---|
| host | `localhost` |
| port | `5432` |
| user | `pgh_ticket` |
| password | `pgh_ticket` |
| database | `pgh_ticket` |

override with `PGH_DATABASE_URL` env var (e.g. `postgresql+asyncpg://user:pass@host:5432/db`).

### tables

- **tickets** — ticket_number, vehicle_make, license_plate, state, issue_date, location, violation, amount_due, officer, status, etc.
- **scans** — range_start, range_end, until_date, tickets_found, errors, duration_s
- **error_logs** — number, command, error_type, retries, resolved state
- **locations** — raw_location, address, latitude, longitude, geocoded_at
- **clusters** — pre-computed probe intervals for the sync command

### schema migrations

managed with alembic. after pulling changes:

```sh
uv run alembic upgrade head
```

new migrations are auto-generated with `uv run alembic revision --autogenerate -m "description"`.

## setup

```sh
uv sync
uv run pgh-ticket --help
```

requires python 3.13+ and `uv`.

### docker compose (postgres)

a `compose.yaml` is included for local development:

```sh
docker compose up -d
uv run alembic upgrade head
```

## proxy

mullvad socks5 proxy avoids ip-based rate limiting.

```sh
uv run pgh-ticket scan ... --proxy socks5://10.64.0.1:1080
uv run pgh-ticket backfill details -w 40 --proxy socks5://10.64.0.1:1080,socks5://10.64.0.2:1080
```

proxies are comma-separated. pass multiple URLs in a single `--proxy` value. without proxy, keep concurrency low (`-w 3`). direct ip with 50 workers → permanent 403 ban.

generate a proxy list:

```sh
uv run scripts/parse_mullvad_proxies.py --limit 50
```

## configuration

env vars:

| var | default | description |
|---|---|---|
| `PGH_DATABASE_URL` | `postgresql+asyncpg://pgh_ticket:pgh_ticket@localhost:5432/pgh_ticket` | postgres connection string |
| `PGH_PROXY_URL` | — | default socks5 proxy |
| `PGH_MAPBOX_TOKEN` | — | mapbox access token for geocoding |

## project structure

```
src/pgh_ticket/
  cli.py              entry point, cyclopts app
  commands/           all subcommands
    lookup.py
    list.py
    stats.py
    scan/             two-phase scanner
    sync/             date-filtered probe
    backfill/         enrichment commands
    errors/           error management
  config/             pydantic-settings configs
  core/
    database.py       async sqlalchemy wrapper
    client/           portal http client, pool, types
    workers.py        concurrent worker pool
    utils.py          batch_flush, resolve_proxy
    fmt.py            progress bars, tables, output
  models/             sqlalchemy orm models
  repos/              data access layer
```

## license

mit
