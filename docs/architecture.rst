==================
Architecture
==================

End-to-End Data Flow
====================

How a parking ticket goes from "existing on the city's web portal" to "plotted on a map with full details."

::

   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │   DISCOVER  │────→│   ENRICH    │────→│  GEOCODE    │────→│   DISPLAY   │
   │             │     │             │     │             │     │             │
   │ Probe numbers│     │ Fetch details│    │ Mapbox API  │     │ Dashboard   │
   │ in ranges   │     │ (location,   │     │ (lat/lon)   │     │ + Map       │
   │             │     │  officer)    │     │             │     │             │
   └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘

Step 1: Discover
================

The portal has no search-by-date or list-all endpoint. The only way to find tickets is to guess numbers and see what comes back.

**The problem:** 7.18 million possible numbers. Most are empty.

**The solution:** Two-phase scan.

**Phase 1 — Probe:** Jump through the range at intervals (e.g., every 100 numbers). Each probe calls the search API once. If it returns results, that number is a "hit" — an entry point into a cluster of valid tickets.

**Phase 2 — Deep scan:** For each hit, scan every number in a window around it (±50). This is where the bulk of tickets are found. For each number that returns results, store the basic fields::

   ticket_number, license_plate, state, issue_date, status, amount_due

**What you get after a scan:** ~30k tickets with basic info. No locations yet. No officer names.

Step 2: Enrich
==============

The search API only returns a summary. To get the full picture, each ticket needs a second API call — the "details" page.

**What details gives you:**

- Location (e.g., "400 SIXTH AVE")
- Violation (e.g., "2 No Parking")
- Officer ID
- Notes
- Due date
- Vehicle make

**The backfill details command:** Finds all tickets where ``location`` is empty, re-queries the API for each one, and updates the database.

**Rate limiting matters here.** Each ticket needs one HTTP request. 30k tickets = 30k requests. Without a proxy, this takes days. With a proxy rotation pool, it takes hours.

Step 3: Geocode
================

Now you have location strings like "400 SIXTH AVE" or "2700 SIDNEY ST". To plot them on a map, you need latitude and longitude.

**The geocode command:**

1. Collect all **unique** location strings (deduplicated — not one per ticket)
2. Send each unique location to Mapbox Geocoding API
3. Store the result::

     raw_location → latitude, longitude, normalized_address

**Why deduplicate?** 30k tickets might only have 6k unique locations. 6k API calls instead of 30k.

**What you get after geocode:** A ``locations`` table mapping every street address to coordinates. Tickets join to this table via their ``location`` string.

Step 4: Display
===============

The dashboard reads from the local SQLite database and renders::

- **Stats:** Total tickets, open tickets, amount due, geocoded count
- **Map:** Points plotted from the ``locations`` table (only geocoded tickets show up)
- **Tables:** Top violations, top locations, by state, by status, officer leaderboards
- **Filters:** Officer, year, status, violation, date range — all sync to URL
- **Paginated list:** Every ticket, browsable 100 at a time

**The map only shows tickets that made it through all 4 steps.** If a ticket hasn't been geocoded yet, it won't appear on the map — but it still shows in the tables and lists.

Data Pipeline Summary
=====================

+------------------+----------------------------+---------------------------+
| Step             | Input                      | Output                    |
+==================+============================+===========================+
| Scan             | Range of ticket numbers    | ~30k tickets (basic info) |
+------------------+----------------------------+---------------------------+
| Backfill details | Tickets with empty location| ~30k tickets (full info)   |
+------------------+----------------------------+---------------------------+
| Geocode          | Unique location strings    | ~6k locations (lat/lon)   |
+------------------+----------------------------+---------------------------+
| Dashboard        | SQLite database            | Stats, map, tables, list  |
+------------------+----------------------------+---------------------------+

Why This Pipeline?
==================

The portal's API is designed for one-off lookups, not bulk collection. Each ticket requires 2 API calls (search + details). The two-phase scan minimizes the first call by skipping voids. Deduplication minimizes the geocode call by only hitting unique addresses.

Without these optimizations, collecting 30k tickets would require ~14M API calls. With them, it's ~60k calls — a 200x reduction.
