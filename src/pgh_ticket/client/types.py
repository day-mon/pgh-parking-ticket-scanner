from __future__ import annotations

import re
from typing import Self

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from pgh_ticket.utils import TicketView


def _notranslate(td) -> str:
    span = td.find("span", class_="notranslate")
    return span.get_text(strip=True) if span else td.get_text(strip=True)


def _ticket_key(td) -> str:
    btn = td.find("button")
    if not btn:
        return ""
    onclick = btn.get("onclick", "")
    if m := re.search(r"(?:value[=:]\s*['\"]?|attr\(['\"]value['\"],\s*['\"]?)(\d+)", onclick):
        return m.group(1)
    return ""


_FIELD_MAP: dict[str, str] = {
    "ticket number": "number",
    "ticket type": "ticket_type",
    "license plate": "license_plate",
    "state or province": "state",
    "issue date": "issue_date",
    "vehicle make": "vehicle_make",
    "location": "location",
    "violation": "violation",
    "amount due": "amount_due",
    "due date": "due_date",
    "officer": "officer",
    "notes": "notes",
    "status": "status",
}


def _field_key(label: str) -> str:
    return _FIELD_MAP.get(label.strip().lower(), label.strip().lower().replace(" ", "_"))


class TicketData(BaseModel):
    """Shared base for search results and detail pages."""

    model_config = ConfigDict(populate_by_name=True)

    number: str = ""
    ticket_type: str = Field(default="", alias="type")
    license_plate: str = Field(default="", alias="plate")
    state: str = ""
    issue_date: str = ""
    location: str = ""
    violation: str = ""
    amount_due: str = Field(default="", alias="amount")
    due_date: str = ""
    officer: str = ""
    notes: str = ""
    status: str = ""
    vehicle_make: str = ""
    ticket_key: str = ""

    def merge(self, other: TicketData) -> Self:
        """Return a new instance with non-empty fields from ``other`` overlaid."""
        overrides = {k: v for k, v in other.model_dump(by_alias=False).items() if v and v.strip()}
        return self.model_copy(update=overrides)

    def to_ticket_view(self) -> TicketView:
        return TicketView(
            number=self.number,
            vehicle_make=self.vehicle_make,
            license_plate=self.license_plate,
            state=self.state,
            issue_date=self.issue_date,
            location=self.location,
            violation=self.violation,
            amount_due=self.amount_due,
            due_date=self.due_date,
            officer=self.officer,
            notes=self.notes,
            status=self.status,
            ticket_type=self.ticket_type,
            ticket_key=self.ticket_key,
        )


class SearchResult(TicketData):
    """Parsed from the search-results table."""

    @classmethod
    def from_html(cls, html: str) -> list[SearchResult]:
        if "No records found" in html:
            return []

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="SearchResultTable")
        if not table:
            return []
        tbody = table.find("tbody")
        if not tbody:
            return []

        results: list[SearchResult] = []
        for row in tbody.find_all("tr"):
            tds = row.find_all("td")
            if len(tds) < 8:
                continue
            results.append(
                cls(
                    number=_notranslate(tds[1]),
                    type=_notranslate(tds[2]),
                    plate=_notranslate(tds[3]),
                    state=_notranslate(tds[4]),
                    issue_date=_notranslate(tds[5]),
                    status=_notranslate(tds[6]),
                    amount=_notranslate(tds[7]),
                    ticket_key=_ticket_key(tds[1]),
                )
            )
        return results


class TicketDetail(TicketData):
    """Parsed from the ticket detail page."""

    @classmethod
    def from_html(cls, html: str) -> TicketDetail | None:
        soup = BeautifulSoup(html, "lxml")
        fields: dict[str, str] = {}

        labels = soup.find_all("div", class_="ticket-details__label")
        for label_div in labels:
            label = label_div.get_text(strip=True).rstrip(":")
            value_div = label_div.find_next_sibling("div", class_="ticket-details__value")
            if value_div:
                value = value_div.get_text(strip=True)
                if value and value.lower() != label.lower():
                    fields[_field_key(label)] = value

        if not fields:
            for row in soup.find_all("div", class_="row"):
                cols = row.find_all("div", class_=lambda c: bool(c and "col" in c))
                for i in range(0, len(cols) - 1, 2):
                    label = cols[i].get_text(strip=True).rstrip(":")
                    value = cols[i + 1].get_text(strip=True) if i + 1 < len(cols) else ""
                    if label and value and label.lower() != value.lower():
                        fields[_field_key(label)] = value

        return cls(**fields) if fields else None
