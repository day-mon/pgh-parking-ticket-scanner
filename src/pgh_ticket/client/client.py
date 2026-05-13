from __future__ import annotations

import asyncio
import re
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
    _RETRY_OPTS = ExponentialRetry(
        attempts=3,
        statuses={403, 429, 500, 502, 503, 504},
        start_timeout=1.0,
        max_timeout=8.0,
        factor=2.0,
    )
    _FIELD_MAP = {
        "ticket number": "number",
        "ticket": "number",
        "vehicle make": "vehicle_make",
        "vehicle": "vehicle_make",
        "license plate": "license_plate",
        "license": "license_plate",
        "plate": "license_plate",
        "state or province": "state",
        "state": "state",
        "issue date": "issue_date",
        "issued": "issue_date",
        "location": "location",
        "violation": "violation",
        "amount due": "amount_due",
        "amount": "amount_due",
        "due date": "due_date",
        "officer": "officer",
        "officer id": "officer",
        "notes": "notes",
        "status": "status",
        "ticket type": "ticket_type",
        "type": "ticket_type",
    }

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        self._retry: RetryClient | None = None
        self._primed = False
        self._closed = False
        self._prime_lock = asyncio.Lock()

        trace = aiohttp.TraceConfig()
        trace.on_request_start.append(self._maybe_prime)
        self._trace_configs = [trace]

    async def _maybe_prime(self, session: aiohttp.ClientSession, _ctx: Any, params: aiohttp.TraceRequestStartParams) -> None:
        if self._primed:
            return
        if params.url.path == "/pittsburgh/":
            return
        async with self._prime_lock:
            if self._primed:
                return
            async with session.get("/pittsburgh/", timeout=aiohttp.ClientTimeout(total=15)):
                pass
            self._primed = True

    @property
    def session(self) -> RetryClient:
        if self._closed:
            raise RuntimeError("client has been closed")
        if self._retry is not None:
            return self._retry
        conn = ProxyConnector.from_url(self.proxy, ssl=_SSL) if self.proxy else aiohttp.TCPConnector(ssl=_SSL)
        sess = aiohttp.ClientSession(
            base_url=self.BASE,
            connector=conn,
            headers=self._HEADERS,
            trace_configs=self._trace_configs,
        )
        self._retry = RetryClient(sess, retry_options=self._RETRY_OPTS)
        return self._retry

    @staticmethod
    def _token() -> str:
        chars = string.ascii_letters + string.digits + "-_"
        return "03AFcWeA" + "".join(secrets.choice(chars) for _ in range(120))

    @staticmethod
    def _strip(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s).strip()

    @staticmethod
    def _span(s: str) -> str:
        return (
            m.group(1).strip()
            if (m := re.search(
                r"<span[^>]*class=['\"]notranslate['\"][^>]*>(.*?)</span>",
                s, re.DOTALL,
            ))
            else Client._strip(s)
        )

    @staticmethod
    def _key(html: str) -> str | None:
        if m := re.search(r"TicketToViewKey.*?value[=:]\s*['\"]?(\d+)['\"]?", html):
            return m.group(1)
        return None

    def _field_key(self, label: str) -> str:
        return self._FIELD_MAP.get(label.strip().lower(), label.strip().lower().replace(" ", "_"))

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
        async with self.session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def search(self, ticket_number: str) -> list[SearchResult]:
        html = await self._request("/pittsburgh/home/dosearch", data={
            "SearchBy": "ticketNumber",
            "IssueNumber": ticket_number,
            "LicPlate": "",
            "LicState": "",
            "GoogleRecaptchaToken": self._token(),
            "X-Requested-With": "XMLHttpRequest",
        })
        return self._parse_search(html)

    def _parse_search(self, html: str) -> list[SearchResult]:
        if "No records found" in html or "<tbody>" not in html:
            return []
        if not (tbody := re.search(r"<tbody>(.*?)</tbody>", html, re.DOTALL)):
            return []

        tickets: list[SearchResult] = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1), re.DOTALL):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(tds) < 8:
                continue
            ticket: SearchResult = {
                "number": self._span(tds[1]),
                "type": self._span(tds[2]),
                "plate": self._span(tds[3]),
                "state": self._span(tds[4]),
                "issue_date": self._span(tds[5]),
                "status": self._span(tds[6]),
                "amount": self._span(tds[7]),
            }
            if key := self._key(tds[1]):
                ticket["ticket_key"] = key
            tickets.append(ticket)

        return tickets

    async def details(self, ticket_key: str) -> TicketDetail | None:
        html = await self._request("/pittsburgh/home/dosearchaction", data={
            "SearchAction": "ShowTicket",
            "TicketToViewKey": ticket_key,
            "DisableCheckBoxes": "False",
            "X-Requested-With": "XMLHttpRequest",
        })
        return self._parse_details(html)

    def _parse_details(self, html: str) -> TicketDetail | None:
        result: dict[str, str] = {}

        for row in re.findall(r'<div[^>]*class=["\']row[^>]*>(.*?)</div>', html, re.DOTALL):
            cols = re.findall(r'<div[^>]*class=["\']col[^>]*>(.*?)</div>', row, re.DOTALL)
            if len(cols) < 2:
                continue
            label = self._strip(cols[0]).rstrip(":")
            value = self._strip(cols[1])
            if label and value and label.lower() != value.lower():
                result[self._field_key(label)] = value

        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
            if len(tds) < 2:
                continue
            label = self._strip(tds[0]).rstrip(":")
            value = self._strip(tds[1])
            if label and value and label.lower() != value.lower():
                result[self._field_key(label)] = value

        return TicketDetail(**result) if result else None

    async def lookup(self, ticket_number: str) -> list[SearchResult]:
        if not (results := await self.search(ticket_number)):
            return results

        for t in results:
            if not (key := t.get("ticket_key")):
                continue
            if details := await self.details(key):
                t.update(details)

        return results
