==================
PGH-Ticket
==================

A tool for collecting and analyzing Pittsburgh parking ticket data from the city's web portal.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   architecture
   scan-algorithm

Overview
========

The Pittsburgh Parking Authority uses a web portal (``dsparkingportal.com/pittsburgh``) to look up tickets by number. Ticket numbers are 7 digits in the range **2,078,060–9,262,307** (~7.18 million possible numbers). Most numbers don't exist — valid tickets cluster in blocks of 10–100+, separated by voids.

There is no list-all or search-by-date endpoint. The only way to find tickets is to probe individual numbers and check what comes back.

Quick Start
===========

.. code-block:: bash

   # Test the client
   pgh-ticket lookup 9244895

   # Scan a range (the heavy lift)
   pgh-ticket scan 8950000-9245300 --until 2026-05-13 -j 20 --step 100

   # Query results
   pgh-ticket list --state PA --status Open -n 20
   pgh-ticket stats
