learnings
=========

things I learned building the pittsburgh parking ticket scanner.

1. captcha tokens are sometimes not validated
---------------------------------------------

some websites dont actually check to see if the captcha value they want
apis to send in is actually valid or not. the pittsburgh parking authority
portal accepts a fake token (``03AFcWeA...`` + 120 random chars). the server
only checks that its non-empty.

2. task groups orchestrate async tasks
---------------------------------------

task groups are used to handle multiple async tasks and coordinate them.
they ensure all tasks finish or cancel on first failure. the kubernetes-to-docker
analogy works at the orchestrator level, but task groups are simpler -- no
health checks, no auto-scaling, no restarts.

3. ``except*`` catches multiple exceptions at once
----------------------------------------------------

introduced in python 3.11. ``except*`` catches an ``ExceptionGroup``, which
bundles multiple exceptions that happened concurrently. regular ``except``
only sees the first one that propagated -- the rest are silently lost.

::

   try:
       async with asyncio.TaskGroup() as tg:
           tg.create_task(fail_one())
           tg.create_task(fail_two())
   except* ValueError as eg:
       print(eg.exceptions)  # all of them, not just the first

you need ``except*`` when using ``TaskGroup`` or ``ExceptionGroup`` --
python raises a runtime error if you try to catch an ``ExceptionGroup``
with plain ``except``.

4. proxy rotation: when your ip gets burned, switch it
--------------------------------------------------------

when scraping, you will get rate-limited or banned. the fix is a pool of
proxies (e.g. mullvad socks5 endpoints). when a request fails with a 403
or timeout, you rotate to the next proxy instead of retrying the same one.

the ``ClientPool`` pattern gives each worker its own session bound to a
different proxy ip. on exception, the client closes the old session and
opens a new one pointing at a different proxy:

::

   async with ClientPool(proxy_list, max_workers) as pool:
       clients = [pool.acquire() for _ in range(workers)]
       results = await resource_map(items, clients, fetch_fn)

you want one session per proxy, not a shared session. different ips =
different rate-limit buckets. if you share one session, you rotate
uselessly -- same ip, same ban.

5. producer-consumer queues are one tool, not the only tool
-------------------------------------------------------------

queues with a producer-consumer model are good for backpressure and
multi-stage pipelines. but they add complexity (serialization, shutdown
signaling). for pure I/O-bound concurrency, structured task groups with
bounded semaphores (like this project's ``resource_map``) are often simpler
and more natural.
