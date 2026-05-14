from __future__ import annotations

import secrets
import ssl
import string
import warnings
from typing import Any

import aiohttp
from aiohttp_retry import ExponentialRetry, RetryClient
from aiohttp_socks import ProxyConnector

from pgh_ticket.client.types import SearchResult, TicketDetail

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


class Client:
    BASE = "https://www.dsparkingportal.com"
    _HEADERS = {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "origin": "https://www.dsparkingportal.com",
        "referer": f"{BASE}/pittsburgh/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "x-requested-with": "XMLHttpRequest",
    }

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._retry: RetryClient | None = None
        self._primed = False
        self._closed = False

    @property
    def session(self) -> RetryClient:
        if self._retry is None:
            connector = (
                ProxyConnector.from_url(self._proxy, ssl=_SSL)
                if self._proxy
                else aiohttp.TCPConnector(ssl=_SSL)
            )
            trace_config = aiohttp.TraceConfig()
            trace_config.on_request_start.append(self._on_request_start)
            session = aiohttp.ClientSession(
                base_url=self.BASE,
                connector=connector,

                trace_configs=[trace_config],

            )
            retry_options = ExponentialRetry(
                attempts=5,
                start_timeout=1,
                max_timeout=30,
                statuses={403, 429, 500, 502, 503, 504},
            )
            self._retry = RetryClient(
                client_session=session,
                retry_options=retry_options,

            )
        return self._retry

    async def _on_request_start(self, *_: Any) -> None:
        if self._primed:
            return
        self._primed = True
        try:
            async with self.session.get(
                "/pittsburgh/", timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                await resp.text()
        except Exception:
            pass

    @staticmethod
    def _token() -> str:
        chars = string.ascii_letters + string.digits + "-_"
        return "03AFcWeA" + "".join(secrets.choice(chars) for _ in range(120))

    async def close(self) -> None:
        self._closed = True
        if self._retry:
            await self._retry.close()
        self._retry = None

    def __del__(self) -> None:
        if self._closed or self._retry is None:
            return
        warnings.warn(
            "Client.session was not closed. Call await client.close() explicitly.",
            ResourceWarning,
            stacklevel=2,
        )

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _request(self, url: str, data: dict) -> str:
        async with self.session.post(
            url, data=data, timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def search(self, ticket_number: str) -> list[SearchResult]:
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

    async def details(self, ticket_key: str) -> TicketDetail | None:
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

    async def lookup(self, ticket_number: str) -> list[SearchResult]:
        results = await self.search(ticket_number)
        if not results:
            return results

        for t in results:
            if not t.ticket_key:
                continue
            if details := await self.details(t.ticket_key):
                t = t.merge(details)

        return results
