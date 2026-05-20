#!/usr/bin/env python3

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import fetch_briefings
import refresh_story_store
import story_store


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill missing Recent history entries.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of missing histories to generate.")
    parser.add_argument("--delay-seconds", type=float, default=0.0, help="Delay between countries.")
    parser.add_argument("--include-existing", action="store_true", help="Refresh existing histories too.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    countries = fetch_briefings.get_country_names()
    if args.include_existing:
        targets = countries
    else:
        targets = []
        for country in countries:
            history = story_store.read_country_history(country)
            if not history:
                targets.append(country)
                continue
            try:
                refresh_story_store.clean_country_history_summary(history.get("summary"), country)
            except RuntimeError:
                targets.append(country)
    if args.limit > 0:
        targets = targets[: args.limit]

    log(f"Starting recent-history backfill: {len(targets)} target countries, {len(countries)} supported countries")
    successes = 0
    failures = 0
    for index, country in enumerate(targets, 1):
        try:
            history = refresh_story_store.refresh_country_history(country)
            successes += 1
            log(f"[{index}/{len(targets)}] OK {country}: {len(history.get('sources', []))} sources")
        except Exception as error:
            failures += 1
            log(f"[{index}/{len(targets)}] FAIL {country}: {error}")
        if args.delay_seconds > 0 and index < len(targets):
            time.sleep(args.delay_seconds)

    log(f"Finished recent-history backfill: {successes} ok, {failures} failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
