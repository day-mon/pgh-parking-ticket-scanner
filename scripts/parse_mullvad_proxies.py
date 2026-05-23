# /// script
# requires-python = ">=3.13"
# ///

"""Parse mullvad-socks-list.txt and output comma-separated socks5:// URLs.

Usage:
    uv run scripts/parse_mullvad_proxies.py --limit 50 > proxies.txt
    uv run scripts/parse_mullvad_proxies.py --limit 50 --source ./mullvad-socks-list.txt > proxies.txt

Then use with pgh-ticket:
    pgh-ticket scan ... --proxy $(cat proxies.txt)
"""

from __future__ import annotations

import argparse
import random
import urllib.request
from pathlib import Path

DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/maximko/mullvad-socks-list/list/"
    "mullvad-socks-list.txt"
)


def parse(text: str) -> list[str]:
    proxies: list[str] = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("Date:") or line.startswith("flag"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        ip = parts[3]
        if "." in ip:
            proxies.append(f"socks5://{ip}:1080")
    return proxies


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse mullvad socks5 proxy list",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Number of proxies to randomly select (0 = all)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE,
        help="URL or local file path to mullvad-socks-list.txt",
    )
    args = parser.parse_args()

    path = Path(args.source)
    if path.exists():
        text = path.read_text()
    else:
        with urllib.request.urlopen(args.source, timeout=30) as resp:
            text = resp.read().decode("utf-8")

    proxies = parse(text)
    if args.limit > 0:
        proxies = random.choices(proxies, k=args.limit)

    print(",".join(proxies))


if __name__ == "__main__":
    main()
