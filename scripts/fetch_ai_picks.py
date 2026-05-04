#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import fetch_briefings


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "generated" / "ai_picks.json"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

WATCHLIST = [
    {
        "id": "taiwan-strait",
        "query": '("Taiwan Strait" OR Taiwan) (military OR drills OR blockade OR naval)',
        "place": "Taiwan Strait",
        "country": "Taiwan / China",
        "region": "East Asia",
        "category": "Security",
        "lat": 24.0,
        "lon": 119.4,
        "importance": 0.9,
    },
    {
        "id": "hormuz",
        "query": '("Strait of Hormuz" OR Hormuz) (shipping OR oil OR tanker OR closure)',
        "place": "Strait of Hormuz",
        "country": "Oman / Iran",
        "region": "Middle East",
        "category": "Energy",
        "lat": 26.57,
        "lon": 56.25,
        "importance": 0.88,
    },
    {
        "id": "red-sea",
        "query": '("Red Sea" OR "Bab el-Mandeb") (shipping OR attacks OR missiles OR Houthis)',
        "place": "Red Sea / Bab el-Mandeb",
        "country": "Yemen / Djibouti",
        "region": "Middle East",
        "category": "Shipping",
        "lat": 13.3,
        "lon": 43.2,
        "importance": 0.84,
    },
    {
        "id": "ukraine",
        "query": '(Ukraine OR Kyiv) (missile OR drone OR ceasefire OR NATO)',
        "place": "Kyiv, Ukraine",
        "country": "Ukraine",
        "region": "Europe",
        "category": "War",
        "lat": 50.4501,
        "lon": 30.5234,
        "importance": 0.86,
    },
    {
        "id": "chad",
        "query": '(Chad OR Ndjamena OR "N Djamena") (security OR election OR Sahel OR Sudan)',
        "place": "N'Djamena, Chad",
        "country": "Chad",
        "region": "Central Africa",
        "category": "Coverage Gap",
        "lat": 12.1348,
        "lon": 15.0557,
        "importance": 0.66,
    },
]


def fetch_gdelt(query: str, limit: int, window_hours: int) -> list[dict]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(limit),
        "timespan": f"{window_hours}hours",
    }
    url = f"{GDELT_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = fetch_briefings.curl_json(url)
    return payload.get("articles", [])


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip()


def source_from_article(article: dict) -> dict:
    domain = article.get("domain") or "GDELT"
    title = clean_title(article.get("title")) or f"Recent coverage from {domain}"
    return {
        "title": title,
        "url": article.get("url") or "",
    }


def build_pick(config: dict, articles: list[dict]) -> dict:
    source = source_from_article(articles[0]) if articles else {
        "title": f"{config['place']} monitoring query",
        "url": "",
    }
    title = source["title"] if articles else f"{config['place']} remains on the watchlist"
    summary = (
        f"Recent open-web coverage around {config['place']} is being tracked as an AI-pick candidate."
        if articles
        else f"No fresh GDELT article matched this watchlist query, but {config['place']} remains a useful monitoring point."
    )
    why = (
        f"This story is pinned to {config['place']} because it can affect {config['region']} and has cross-border relevance."
    )
    return {
        "id": f"{config['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "title": title,
        "summary": summary,
        "whyItMatters": why,
        "lat": config["lat"],
        "lon": config["lon"],
        "place": config["place"],
        "country": config["country"],
        "region": config["region"],
        "category": config["category"],
        "importance": config["importance"],
        "confidence": 0.74 if articles else 0.62,
        "sources": [source],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate cached AI Picks for the globe.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum picks to write.")
    parser.add_argument("--per-query", type=int, default=3, help="Articles to inspect per watchlist query.")
    parser.add_argument("--window-hours", type=int, default=48, help="GDELT lookback window.")
    parser.add_argument("--delay-seconds", type=float, default=6.0, help="Delay between GDELT queries.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    picks = []
    for index, config in enumerate(WATCHLIST):
        if index:
            time.sleep(args.delay_seconds)
        try:
            articles = fetch_gdelt(config["query"], args.per_query, args.window_hours)
        except Exception as error:
            print(f"warning: {config['id']} query failed: {error}", file=sys.stderr)
            articles = []
        picks.append(build_pick(config, articles))

    picks.sort(key=lambda pick: pick["importance"], reverse=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "gdelt-watchlist",
        "windowHours": args.window_hours,
        "picks": picks[: args.limit],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['picks'])} AI picks to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
