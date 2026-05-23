"""Data types for the Pittsburgh parking portal."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from pgh_ticket.core.fmt import TicketView


@dataclass
class SearchResult:
    """Parsed from the search-results table."""

    number: str = ""
    ticket_type: str = ""
    license_plate: str = ""
    state: str = ""
    issue_date: str = ""
    status: str = ""
    amount_due: str = ""
    ticket_key: str = ""
    vehicle_make: str = ""
    location: str = ""
    violation: str = ""
    due_date: str = ""
    officer: str = ""
    notes: str = ""

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
                    ticket_type=_notranslate(tds[2]),
                    license_plate=_notranslate(tds[3]),
                    state=_notranslate(tds[4]),
                    issue_date=_notranslate(tds[5]),
                    status=_notranslate(tds[6]),
                    amount_due=_notranslate(tds[7]),
                    ticket_key=_ticket_key(tds[1]),
                )
            )
        return results

    def to_view(self) -> TicketView:
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


@dataclass
class TicketDetail:
    """Parsed from the ticket detail page."""

    vehicle_make: str = ""
    location: str = ""
    violation: str = ""
    due_date: str = ""
    officer: str = ""
    notes: str = ""

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

        # only keep fields that TicketDetail actually has
        valid = {k: v for k, v in fields.items() if k in cls.__dataclass_fields__}
        return cls(**valid) if valid else None


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
