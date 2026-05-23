# sequencing & architecture

## the problem

the Pittsburgh parking authority uses a web portal (`dsparkingportal.com/pittsburgh`) to look up tickets by number. ticket numbers are 7 digits in the range **2,078,060–9,262,307** (~7.18 million possible numbers). most numbers don't exist — valid tickets cluster in blocks of 10–100+, separated by voids.

there is no list-all or search-by-date endpoint. the only way to find tickets is to probe individual numbers and check what comes back.

## command flow

the typical workflow moves through these commands in order:

```
lookup        test a few known numbers, verify the client works
  ↓
scan          collect all tickets in a range up to a date (the heavy lift)
  ↓
sync          quickly find tickets on one specific date (probe-only, no deep scan)
  ↓
list / stats  query what's in the database
  ↓
backfill      fill in missing detail fields for already-stored tickets
```

### lookup
one-off lookups. takes one or more ticket numbers, hits the api, stores results in the db. useful for testing the client connection before a big scan.

```
pgh-ticket lookup 9244895
pgh-ticket lookup 8950000-8950005 --verbose
```

### scan (the main event)
two-phase collection covering a range of ticket numbers.

```
pgh-ticket scan 8950000-9245300 --until 2026-05-13 -j 20 --step 100
```

**phase 1: probing.** jump through the range at interval `--step` (default 50). each probe calls `search()` on a single number. if the api returns results, that number is a "hit" — an entry point into a cluster of valid tickets. 295k numbers at step=100 → ~2,953 probes.

**phase 2: deep scan.** for each hit, build a window ±(step/2) around it, merge overlapping windows, then scan every number in each merged window. this is where the bulk of tickets are found. for each number that returns results, we also fetch the detail page (officer, location, violation) and upsert everything into the db.

**why two-phase?** single-phase would require 295k requests. most of them would return empty. probing at step=100 cuts phase 1 to ~3k requests. the deep scan then only hits clusters where tickets actually live.

### sync
probe-only, date-filtered. idea: "find every ticket issued on 2026-05-08." 

```
pgh-ticket sync 2026-05-08 --step 200 -j 3
```

probes the full range at step interval. for each result, checks if the issue date matches the target. if it does, stores it and optionally fetches the detail page. no deep scan — ticket numbers are already known from the search result.

includes a circuit breaker: after N consecutive errors, it sleeps (30s, then 3min). useful when running without a proxy.

### list & stats
read-only queries against the local sqlite database.

```
pgh-ticket list --state PA --status Open -n 20
pgh-ticket list --date-from 2026-05-01 --date-to 2026-05-08 --verbose
pgh-ticket stats
```

`list` shows tickets with optional filters (state, status, date range). `stats` shows aggregate breakdowns (by status, by state, open by state, recent scan history).

### backfill
tickets stored without detail fields (officer, location, violation) can be enriched later. backfill finds tickets where `officer` is empty, re-queries the api for each one, and updates the db.

```
pgh-ticket backfill -n 100
```

## two-phase scan in detail

```
range: 2,078,060 → 9,262,307

phase 1: probe every 100 numbers (~71,800 probes)

  2078060  → HIT (1 ticket returned)
  2078160  → empty
  ...

  result: ~30,000 hits across the range

phase 2: merge windows & deep scan

  hit at 2078060 → window 2078010–2078110
  hit at 2078300 → window 2078250–2078350
  → merge as needed

  deep scan every number in each merged window.
  for each, search() + details() → upsert into db.
```

## ticket numbering quirks

- **dates are not monotonic.** 9245000 might be may 1, while 9245300 is april 21. different number blocks are assigned at different times.
- **no modulo pattern.** unlike sf's parking tickets (add-11 rule), pgh tickets cluster unpredictably. the only reliable method is probe + deep-scan around hits.
- **upper bound.** numbers above ~9,262,307 return nothing (no more tickets). the range floor is ~2,078,060. occasionally anomalous numbers appear (e.g. 2,500,000 with a 2024 date), but these are outliers.
- **72-hour lag.** recently issued tickets may not appear for up to 3 days.

## client architecture

### lazy session + traceconfig priming

```python
async with Client(proxy="socks5://10.64.0.1:1080") as cl:
    results = await cl.search("8950000")
    details = await cl.details("some-key")
```

the `Client` class creates an aiohttp `ClientSession` wrapped in `RetryClient` (from `aiohttp-retry`) on first access. `close()` tears it down. `__aenter__`/`__aexit__` enable the context manager.

**priming**: the portal requires an `ASP.NET_SessionId` cookie. instead of an explicit `prime()` call, the client attaches a `TraceConfig.on_request_start` callback that does a GET to `/pittsburgh/` on the very first request. completely transparent to the caller.

### retry & proxy

- **aiohttp-retry**: wraps the session with exponential backoff on 403/429/5xx. no manual retry loops.
- **aiohttp-socks**: socks5 proxy support via `ProxyConnector`. the mullvad proxy (`socks5://10.64.0.1:1080`) avoids IP-based rate limiting.

### recaptcha token

the search form includes a `GoogleRecaptchaToken` field. the server only checks that it's non-empty — any string works. the client generates a fake token with the `03AFcWeA...` prefix + 120 random chars.

### rate limiting

- direct IP with 50 workers → permanent 403 ban for that IP.
- through mullvad proxy, 20 workers is safe. higher concurrency can still trigger rate limits on the proxy's exit IP.
- without proxy, use `-j 3` or lower.

## database

sqlite via sqlalchemy 2.0 (mapped_column style). stored via `platformdirs`:
- linux: `~/.local/share/pgh-ticket/tickets.db`
- macos: `~/Library/Application Support/pgh-ticket/tickets.db`

### schema

**tickets** table:
- `ticket_number` (pk), `vehicle_make`, `license_plate`, `state`, `issue_date`
- `location`, `violation`, `amount_due`, `due_date`, `officer`, `notes`
- `status`, `ticket_type`, `raw_json`
- `first_seen`, `updated_at` (isoformat timestamps)
- indexes: `(state, status)`, `issue_date`, `updated_at`

**scans** table:
- `range_start`, `range_end`, `until_date`, `tickets_found`, `errors`, `duration_s`
- `scanned_at` (isoformat)

### upsert

`Database.upsert_ticket()` accepts either a raw `dict` (from the api) or a `TicketData` dataclass. on insert, it populates all columns. on update, it refreshes every field except `ticket_number`, `first_seen`, and `updated_at` (which auto-updates).

## known pitfalls

- **client closed bug**: the old scan (in `cli.py`) failed with `RuntimeError: client has been closed` because `__aexit__` fired before probes ran. the rewrite moved the `async with Client()` block to surround all async work. fixed.
- **range parameter shadowing**: `range` is both a builtin and was a parameter name. renamed to `number_range`.
- **progress in nohup**: rich progress bars require `force_terminal=True` to render when stderr is piped to a file. set on the `Console` instance.
- **mullvad proxy**: only reachable when connected to the vpn. address is `socks5://10.64.0.1:1080`.
- **python version**: project uses python 3.13. always run via `uv run`.
