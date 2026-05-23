# pgh-ticket

scanner for the **Pittsburgh Parking Authority** ticket portal. probes ticket numbers, scrapes details, stores results in sqlite.

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
pgh-ticket scan 8950000-9245300 --until 2026-05-13 -j 20 --step 100
```

**two-phase scan.** phase 1 probes every `--step` numbers (~3k requests for a 295k range). phase 2 deep-scans merged windows around every hit, fetching details for each ticket. this is the main collection command.

```
pgh-ticket sync 2026-05-08 --step 200 -j 3
```

probe-only, date-filtered. finds tickets for one specific date. no deep scan — just search results filtered by issue date. circuit breaker built in (sleeps on repeated errors).

```
pgh-ticket list --state PA --status Open -n 20
pgh-ticket list --date-from 2026-05-01 --date-to 2026-05-08 --verbose
pgh-ticket stats
```

read-only queries. `list` filters by state, status, date range. `stats` shows aggregate breakdowns and recent scan history.

```
pgh-ticket backfill details -n 100
pgh-ticket backfill keys -n 100
pgh-ticket backfill geocode
```

enrich stored tickets. `details` fetches officer/location/violation for tickets missing them. `keys` fetches the api's internal ticket key. `geocode` turns location strings into lat/lon via mapbox.

```
pgh-ticket errors list
pgh-ticket errors stats
pgh-ticket errors clear
pgh-ticket errors retry
```

manage failed lookups. `retry` re-attempts unresolved errors.

## ticket numbering quirks

- **dates are not monotonic.** 9245000 might be may 1, 9245300 might be april 21. different blocks assigned at different times.
- **no modulo pattern.** unlike some cities (sf's add-11 rule), pgh tickets cluster unpredictably. only reliable method: probe + deep-scan.
- **upper bound:** ~9,262,307. lower bound: ~2,078,060.
- **72-hour lag.** recently issued tickets may not appear for up to 3 days.

## database

sqlite via sqlalchemy 2.0 async. stored at:

| os | path |
|---|---|
| macos | `~/Library/Application Support/pgh-ticket/tickets.db` |
| linux | `~/.local/share/pgh-ticket/tickets.db` |

override with `--db /path/to/tickets.db`.

### tables

- **tickets** — ticket_number, vehicle_make, license_plate, state, issue_date, location, violation, amount_due, officer, status, etc.
- **scans** — range_start, range_end, until_date, tickets_found, errors, duration_s
- **error_logs** — number, command, error_type, retries, resolved state
- **locations** — raw_location, address, latitude, longitude, geocoded_at
- **clusters** — pre-computed probe intervals for the sync command

## setup

```sh
uv sync
uv run pgh-ticket --help
```

requires python 3.13+ and `uv`.

## proxy

mullvad socks5 proxy avoids ip-based rate limiting.

```sh
uv run pgh-ticket scan ... --proxy socks5://10.64.0.1:1080
```

without proxy, keep concurrency low (`-j 3`). direct ip with 50 workers → permanent 403 ban.

generate a proxy list:

```sh
uv run scripts/parse_mullvad_proxies.py --limit 50 > proxies.txt
```

## configuration

env vars with `PGH_` prefix:

| var | default | description |
|---|---|---|
| `PGH_DB_PATH` | (platformdirs) | sqlite path |
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
