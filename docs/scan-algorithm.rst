==================
Two-Phase Scan Algorithm
==================

The Problem
===========

The portal has ~7.18 million possible ticket numbers (2,078,060–9,262,307). Probing every number would require 7M+ HTTP requests. Most return empty — valid tickets cluster in blocks of 10–100+, separated by voids of thousands.

The Solution
============

A two-phase approach that probes sparsely, then deep-scans only around hits.

Phase 1: Probing
================

Jump through the range at interval ``--step`` (default 50). Each probe calls ``search()`` on a single number.

Example with step=100::

   2078060  → HIT (1 ticket returned)
   2078160  → empty
   2078260  → empty
   2078360  → HIT (3 tickets)
   ...

For a 295k-number range at step=100: ~2,953 probes.

Phase 2: Deep Scan
==================

For each hit, build a window ±(step/2) around it::

   hit at 2078060 → window 2078010–2078110
   hit at 2078360 → window 2078310–2078410

Merge overlapping windows, then scan **every number** in each merged window. For each number that returns results, also fetch the detail page (officer, location, violation) and upsert into the database.

Why Two-Phase?
==============

+----------------+------------------+------------------+
| Approach       | Requests (295k)  | Time (est.)      |
+================+==================+==================+
| Single-phase   | 295,000          | ~8 hours         |
| Two-phase      | ~3,000 + ~50k    | ~45 minutes      |
+----------------+------------------+------------------+

The deep scan only hits clusters where tickets actually live. The voids between clusters are skipped entirely.

Ticket Numbering Quirks
=======================

- **Dates are not monotonic** — 9245000 might be May 1, while 9245300 is April 21. Different number blocks are assigned at different times.
- **No modulo pattern** — Unlike SF's parking tickets (add-11 rule), PGH tickets cluster unpredictably.
- **Upper bound** — Numbers above ~9,262,307 return nothing.
- **72-hour lag** — Recently issued tickets may not appear for up to 3 days.

Window Merging
==============

Adjacent or overlapping windows are merged to avoid duplicate work::

   hit at 2078060 → window 2078010–2078110
   hit at 2078300 → window 2078250–2078350
   → NOT overlapping, keep separate

   hit at 2078060 → window 2078010–2078110
   hit at 2078090 → window 2078040–2078140
   → OVERLAPPING, merge to 2078010–2078140

Implementation
==============

The scan command lives in ``commands/scan/``::

   scanner.py:
       - probe_phase()     # jump through range, collect hits
       - build_windows()   # ±(step/2) around each hit
       - merge_windows()   # collapse overlaps
       - deep_scan()       # scan every number in merged windows

   window.py:
       - Window dataclass
       - merge_overlapping() helper

Rate Limiting
=============

- Direct IP with 50 workers → permanent 403 ban
- Through Mullvad proxy (``socks5://10.64.0.1:1080``), 20 workers is safe
- Without proxy, use ``-j 3`` or lower

The ``WorkerPool`` handles concurrency limiting via ``asyncio.Semaphore``.
