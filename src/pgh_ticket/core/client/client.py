"""HTTP client for the Pittsburgh parking portal."""

from __future__ import annotations

import datetime
import secrets
import string
import uuid
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any

import aiohttp
import aiohttp_retry
from aiohttp import TraceRequestEndParams, TraceRequestStartParams
from aiohttp_retry import RetryClient
from aiohttp_socks import ProxyConnector

from pgh_ticket.config import portal
from pgh_ticket.core.client.types import SearchResult, TicketDetail

_CHROME_VERSIONS: tuple[int, ...] = tuple(range(120, 125))
_FIREFOX_VERSIONS: tuple[int, ...] = tuple(range(122, 127))
_SAFARI_WEBKIT_VERSIONS: tuple[tuple[str, str], ...] = (
    ("605.1.15", "17.4.1"),
    ("605.1.15", "17.5"),
    ("605.1.15", "17.6"),
)
_MAC_OS_VERSIONS: tuple[str, ...] = ("10_15_7", "14_0", "14_1", "14_4_1", "14_5")
_WIN_OS = "Windows NT 10.0; Win64; x64"
_LINUX_OS = "X11; Linux x86_64"


def _random_ua() -> str:
    browser = secrets.choice(("chrome", "firefox", "safari"))

    if browser == "chrome":
        os = secrets.choice(
            (
                f"Macintosh; Intel Mac OS X {secrets.choice(_MAC_OS_VERSIONS)}",
                _WIN_OS,
                _LINUX_OS,
            )
        )
        v = secrets.choice(_CHROME_VERSIONS)
        return f"Mozilla/5.0 ({os}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36"

    if browser == "firefox":
        os = secrets.choice(
            (
                f"Macintosh; Intel Mac OS X {secrets.choice(_MAC_OS_VERSIONS)}",
                _WIN_OS,
                _LINUX_OS,
            )
        )
        v = secrets.choice(_FIREFOX_VERSIONS)
        return f"Mozilla/5.0 ({os}; rv:{v}.0) Gecko/20100101 Firefox/{v}.0"

    # safari — mac only
    mac = secrets.choice(_MAC_OS_VERSIONS)
    webkit, safari = secrets.choice(_SAFARI_WEBKIT_VERSIONS)
    return f"Mozilla/5.0 (Macintosh; Intel Mac OS X {mac}) AppleWebKit/{webkit} (KHTML, like Gecko) Version/{safari} Safari/{webkit}"


HEADERS: MappingProxyType[str, str] = MappingProxyType(
    {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.dsparkingportal.com",
        "referer": "https://www.dsparkingportal.com/pittsburgh/",
        "x-requested-with": "XMLHttpRequest",
    }
)

RETRY_STATUSES: set[int] = {403, 429, 500, 502, 503, 504}


class ProxyRotator:
    """Holds a list of SOCKS5 proxies and returns one on each call."""

    def __init__(self, proxies: list[str]) -> None:
        import random

        self._proxies = proxies
        random.shuffle(self._proxies)
        self._index = 0

    def next(self) -> str:
        p = self._proxies[self._index % len(self._proxies)]
        self._index += 1
        return p

    def __len__(self) -> int:
        return len(self._proxies)


class PortalClient:
    """Async HTTP client for the Pittsburgh parking portal."""

    def __init__(
        self,
        proxy: str | list[str] | None = None,
        *,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        if isinstance(proxy, list):
            self._rotator = ProxyRotator(proxy)
            self._proxy = self._rotator.next()
        else:
            self._rotator = None
            self._proxy = proxy
        self._on_error = on_error
        self._retry: RetryClient | None = None
        self._log_file: Any = None

    def _build_session(self) -> RetryClient:
        connector = (
            ProxyConnector.from_url(self._proxy, limit_per_host=25)
            if self._proxy
            else aiohttp.TCPConnector(limit_per_host=25)
        )
        session = aiohttp.ClientSession(
            base_url=portal.settings.portal_base,
            connector=connector,
            headers={**HEADERS, "user-agent": _random_ua()},
            raise_for_status=True,
            trace_configs=[_make_trace(self._log_file)],
        )

        return RetryClient(
            client_session=session,
            retry_options=aiohttp_retry.ExponentialRetry(
                attempts=5,
                start_timeout=1,
                max_timeout=30,
                statuses=RETRY_STATUSES,
            ),
        )

    @property
    def session(self) -> RetryClient:
        if self._retry is None:
            self._retry = self._build_session()
        return self._retry

    async def rotate(self) -> None:
        """Close current session and switch to next proxy in pool."""
        if self._retry:
            await self._retry.close()
            self._retry = None
        if self._rotator:
            self._proxy = self._rotator.next()

    async def close(self) -> None:
        if self._retry:
            await self._retry.close()
            self._retry = None
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    async def __aenter__(self) -> PortalClient:
        self._log_file = Path(f"/tmp/pgh-ticket-{uuid.uuid4().hex[:8]}.log").open(
            "a", encoding="utf-8"
        )
        try:
            async with self.session.get("/pittsburgh/", timeout=aiohttp.ClientTimeout(total=30)):
                pass
        except Exception:
            pass
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _request(self, url: str, data: dict) -> str:
        async with self.session.post(
            url, data=data, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            return await resp.text()

    @staticmethod
    def _token() -> str:
        chars = string.ascii_letters + string.digits + "-_"
        return "03AFcWeA" + "".join(secrets.choice(chars) for _ in range(120))

    async def search(self, ticket_number: str) -> list[SearchResult]:
        try:
            html = await self._request(
                "/pittsburgh/home/dosearch",
                data={
                    "SearchBy": "ticketNumber",
                    "IssueNumber": ticket_number,
                    "LicPlate": "",
                    "LicState": "",
                    "GoogleRecaptchaToken": self._token(),
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            return SearchResult.from_html(html)
        except Exception as exc:
            if self._on_error:
                self._on_error(ticket_number, exc)
            raise

    async def details(self, ticket_key: str) -> TicketDetail | None:
        try:
            html = await self._request(
                "/pittsburgh/home/dosearchaction",
                data={
                    "SearchAction": "ShowTicket",
                    "TicketToViewKey": ticket_key,
                    "DisableCheckBoxes": "False",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            return TicketDetail.from_html(html)
        except Exception as exc:
            if self._on_error:
                self._on_error(ticket_key, exc)
            raise

    async def lookup(self, ticket_number: str) -> list[SearchResult]:
        """Search + fetch details for each result."""
        results = await self.search(ticket_number)
        enriched: list[SearchResult] = []
        for r in results:
            if not r.ticket_key:
                continue
            try:
                detail = await self.details(r.ticket_key)
            except Exception as exc:
                if self._on_error:
                    self._on_error(r.ticket_key, exc)
                continue
            if detail:
                r = _merge_detail(r, detail)
            enriched.append(r)
        return enriched


def _merge_detail(result: SearchResult, detail: TicketDetail) -> SearchResult:
    """Overlay non-empty detail fields onto a search result."""
    return SearchResult(
        number=result.number,
        ticket_type=result.ticket_type,
        license_plate=result.license_plate,
        state=result.state,
        issue_date=result.issue_date,
        status=result.status,
        amount_due=result.amount_due,
        ticket_key=result.ticket_key,
        vehicle_make=detail.vehicle_make or result.vehicle_make,
        location=detail.location or result.location,
        violation=detail.violation or result.violation,
        due_date=detail.due_date or result.due_date,
        officer=detail.officer or result.officer,
        notes=detail.notes or result.notes,
    )


def _make_trace(log_file) -> aiohttp.TraceConfig:
    async def on_request_start(
        _session: aiohttp.ClientSession,
        _ctx: TraceRequestStartParams,
        params: TraceRequestStartParams,
    ) -> None:
        ts = datetime.datetime.now(datetime.UTC).isoformat()
        log_file.write(
            f"[{ts}] REQ  {params.method} {params.url} data={getattr(params, 'data', None)!r}\n"
        )
        log_file.flush()

    async def on_request_end(
        _session: aiohttp.ClientSession,
        _ctx: TraceRequestEndParams,
        params: TraceRequestEndParams,
    ) -> None:
        ts = datetime.datetime.now(datetime.UTC).isoformat()
        text = await params.response.text()
        log_file.write(
            f"[{ts}] RESP status={params.response.status} len={len(text)} preview={text[:500].replace(chr(10), ' ')!r}\n"
        )
        log_file.flush()

    trace = aiohttp.TraceConfig()
    trace.on_request_start.append(on_request_start)
    trace.on_request_end.append(on_request_end)
    return trace
