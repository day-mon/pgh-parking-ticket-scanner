"""Async worker pool using AnyIO for structured concurrency."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from anyio import create_memory_object_stream, create_task_group
from anyio.streams.memory import MemoryObjectSendStream
from rich.progress import Progress, TaskID

type ErrorHandler[T] = Callable[[Exception, T], Awaitable[None] | None] | None


@dataclass
class WorkerPool[T, R]:
    """Concurrent worker pool with semaphore-limited HTTP requests."""

    workers: int
    progress: Progress | None = None
    task_id: TaskID | None = None

    sem: asyncio.Semaphore = field(init=False)
    lock: asyncio.Lock = field(init=False)
    errors: int = field(default=0, init=False)
    done: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.sem = asyncio.Semaphore(self.workers)
        self.lock = asyncio.Lock()

    async def __aenter__(self) -> WorkerPool[T, R]:
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    async def map(
        self,
        items: Iterable[T],
        fn: Callable[[T], Awaitable[R]],
        *,
        on_error: ErrorHandler[T] = None,
    ) -> list[R]:
        """Run ``fn`` over ``items`` with concurrency limiting."""
        results: list[R] = []

        async with create_task_group() as tg:
            for item in items:
                tg.start_soon(self._map_worker, item, fn, results, on_error)

        return results

    async def pipeline(
        self,
        items: Iterable[T],
        producer: Callable[[T], Awaitable[R | None]],
        consumer: Callable[[R], Awaitable[Any]] | None = None,
        *,
        on_error: ErrorHandler[T] = None,
    ) -> list[R]:
        """Producer/consumer with optional second stage."""
        collected: list[R] = []
        send_stream, receive_stream = create_memory_object_stream[R](max_buffer_size=self.workers)

        async with create_task_group() as tg:
            if consumer is not None:
                for _ in range(self.workers):
                    tg.start_soon(self._pipeline_consumer, receive_stream, consumer)

            for item in items:
                tg.start_soon(
                    self._pipeline_producer, item, producer, collected, send_stream, on_error
                )

        return collected

    async def _map_worker(
        self,
        item: T,
        fn: Callable[[T], Awaitable[R]],
        results: list[R],
        on_error: ErrorHandler[T],
    ) -> None:
        try:
            async with self.sem:
                result = await fn(item)
            async with self.lock:
                self.done += 1
                if result is not None:
                    results.append(result)
                self._advance_progress()
        except* Exception as exc_group:
            async with self.lock:
                self.errors += len(exc_group.exceptions)
                self.done += 1
                self._advance_progress()
            if on_error is not None:
                for exc in exc_group.exceptions:
                    await _maybe_await(on_error(exc, item))

    async def _pipeline_producer(
        self,
        item: T,
        producer: Callable[[T], Awaitable[R | None]],
        collected: list[R],
        send_stream: MemoryObjectSendStream[R],
        on_error: ErrorHandler[T],
    ) -> None:
        try:
            async with self.sem:
                result = await producer(item)
            async with self.lock:
                self.done += 1
                if result is not None:
                    collected.append(result)
                    await send_stream.send(result)
                self._advance_progress()
        except* Exception as exc_group:
            async with self.lock:
                self.errors += len(exc_group.exceptions)
                self.done += 1
                self._advance_progress()
            if on_error is not None:
                for exc in exc_group.exceptions:
                    await _maybe_await(on_error(exc, item))

    async def _pipeline_consumer(
        self,
        receive_stream,
        consumer: Callable[[R], Awaitable[Any]] | None,
    ) -> None:
        async with receive_stream:
            async for value in receive_stream:
                if consumer is not None:
                    try:
                        async with self.sem:
                            await consumer(value)
                    except Exception:
                        pass

    def _advance_progress(self) -> None:
        if self.progress and self.task_id is not None:
            status = f"{self.done} done"
            if self.errors:
                status += f" • {self.errors} errors"
            self.progress.update(self.task_id, advance=1, status=status)


async def _maybe_await(value: Awaitable[None] | None) -> None:
    if asyncio.iscoroutine(value):
        await value


async def resource_map[T, R, Resource](
    items: list[T],
    resources: list[Resource],
    fn: Callable[[Resource, T], Awaitable[R | None]],
    *,
    progress: Progress | None = None,
    task_id: TaskID | None = None,
) -> tuple[list[R], list[T]]:
    """Map ``fn`` over ``items`` using dedicated ``resources`` per worker.

    Each worker is assigned one ``Resource`` from the list, then pulls
    items from a shared queue.  ``fn`` should handle its own retry logic.
    Items that raise or return ``None`` are collected in the second list.

    Returns ``(results, failed_items)``.
    """
    workers = len(resources)
    queue: asyncio.Queue[T | None] = asyncio.Queue()
    for item in items:
        await queue.put(item)
    for _ in range(workers):
        await queue.put(None)

    results: list[R] = []
    failed: list[T] = []
    done = [0]
    stored = [0]
    errors = [0]
    lock = asyncio.Lock()

    async def _worker(resource: Resource) -> None:
        while True:
            item = await queue.get()
            if item is None:
                break
            try:
                result = await fn(resource, item)
                if result is not None:
                    async with lock:
                        results.append(result)
                        stored[0] += 1
                else:
                    async with lock:
                        failed.append(item)
            except Exception:
                async with lock:
                    failed.append(item)
                    errors[0] += 1
            async with lock:
                done[0] += 1
                if progress and task_id is not None:
                    status = f"{done[0]} done"
                    if stored[0]:
                        status += f" • {stored[0]} stored"
                    if errors[0]:
                        status += f" • {errors[0]} errors"
                    progress.update(task_id, advance=1, status=status)

    await asyncio.gather(*[_worker(r) for r in resources])
    return results, failed
