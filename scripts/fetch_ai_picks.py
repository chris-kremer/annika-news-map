#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import fetch_briefings


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "generated" / "ai_picks.json"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

UNDERLOOKED_STORY_DESK = [
    {
        "id": "mali-coordinated-attacks",
        "query": '(Mali OR Bamako) ("coordinated attacks" OR JNIM OR Azawad OR coup)',
        "fallbackTitle": "Mali's late-April attacks look bigger than a routine insurgent flare-up",
        "summary": "Coordinated attacks around Bamako and several regional cities put pressure on Mali's junta and its Russian-backed security model.",
        "whyItMatters": "This is the kind of Sahel story that can move fast without leading global homepages: a capital-security shock, junta legitimacy, rebel-jihadist coordination, and spillover risk for Niger and Burkina Faso.",
        "angle": "Fresh capital-security shock after coordinated nationwide attacks.",
        "freshness": "New escalation",
        "place": "Bamako, Mali",
        "country": "Mali",
        "region": "West Africa",
        "category": "Underlooked conflict",
        "lat": 12.6392,
        "lon": -8.0029,
        "importance": 0.9,
        "overlap": [{"type": "ongoing-conflict", "label": "Sahel instability"}],
        "sources": [
            {
                "title": "Gunmen stage simultaneous attacks across Mali, army says",
                "url": "https://www.aljazeera.com/news/2026/4/25/mali-army-says-armed-groups-launch-nationwide-attacks-gunfire-near-airport",
            }
        ],
    },
    {
        "id": "ecuador-curfew-gangs",
        "query": '(Ecuador OR Guayaquil OR Quito) (curfew OR gangs OR "state of emergency" OR violence)',
        "fallbackTitle": "Ecuador extends curfews as gang violence becomes a governance problem",
        "summary": "A fresh curfew across nine provinces shows Ecuador's security emergency is no longer just a crime story; it is shaping daily economic life and state capacity.",
        "whyItMatters": "Ecuador rarely stays in the international top slot, but the combination of ports, cocaine routes, emergency rule, and economic disruption makes this a strategic Latin America watch item.",
        "angle": "Gang pressure is forcing emergency governance across major provinces.",
        "freshness": "Fresh policy move",
        "place": "Guayaquil / Quito, Ecuador",
        "country": "Ecuador",
        "region": "South America",
        "category": "Organized crime",
        "lat": -2.19,
        "lon": -79.889,
        "importance": 0.84,
        "overlap": [],
        "sources": [
            {
                "title": "Noboa decreta 15 días de toque de queda en nueve provincias",
                "url": "https://elpais.com/america/2026-05-02/noboa-decreta-15-dias-de-toque-de-queda-en-nueve-provincias-y-reaviva-el-choque-con-los-sectores-productivos.html",
            }
        ],
    },
    {
        "id": "haiti-gang-territory",
        "query": '(Haiti OR "Port-au-Prince") (gangs OR "territory controlled" OR "Viv ansanm")',
        "fallbackTitle": "Haiti's gang map is shifting, but armed groups still dominate the capital",
        "summary": "Local police leadership says gangs control less of metropolitan Port-au-Prince than before, yet the reported 72% figure still points to a capital where armed groups shape movement, services, and politics.",
        "whyItMatters": "The interesting part is not simply that Haiti is violent; it is whether small territorial reversals change the balance before the international security mission winds down.",
        "angle": "A granular update on territorial control, not another generic Haiti-is-in-crisis card.",
        "freshness": "Recent local update",
        "place": "Port-au-Prince, Haiti",
        "country": "Haiti",
        "region": "Caribbean",
        "category": "State capacity",
        "lat": 18.5944,
        "lon": -72.3074,
        "importance": 0.8,
        "overlap": [],
        "sources": [
            {
                "title": "PNH Chief Says Gangs Control 72% of Metropolitan Area",
                "url": "https://lenouvelliste.com/en/article/266079/les-gangs-controlent-72-de-la-zone-metropolitaine-selon-le-directeur-general-de-la-pnh",
            }
        ],
    },
    {
        "id": "southern-africa-drought",
        "query": '("Southern Africa" OR Zambia OR Malawi OR Zimbabwe) (drought OR hydropower OR food security)',
        "fallbackTitle": "Southern Africa's drought is turning into a power, food, and budget story",
        "summary": "Drought pressure across parts of Southern Africa keeps showing up as hydropower shortages, food insecurity, and fiscal strain rather than one dramatic breaking-news event.",
        "whyItMatters": "Slow disasters are easy to miss. This one matters because electricity, crops, debt, and migration pressure can reinforce each other across borders.",
        "angle": "Slow-moving drought effects that compound across energy and food systems.",
        "freshness": "Slow-burn risk",
        "place": "Lusaka, Zambia",
        "country": "Zambia / Southern Africa",
        "region": "Southern Africa",
        "category": "Climate stress",
        "lat": -15.3875,
        "lon": 28.3228,
        "importance": 0.73,
        "overlap": [],
        "sources": [
            {
                "title": "Southern Africa drought monitoring query",
                "url": "https://reliefweb.int/disasters?advanced-search=%28D48535%29_%28F10%29",
            }
        ],
    },
    {
        "id": "chad-sudan-spillover",
        "query": '(Chad OR "N Djamena" OR Adre) (Sudan OR refugees OR border OR Darfur)',
        "fallbackTitle": "Chad is the overlooked pressure valve for Sudan's war",
        "summary": "The Chad-Sudan border is carrying refugee flows, cross-border security risk, and political strain that rarely gets separated from the broader Sudan war headline.",
        "whyItMatters": "If Sudan is already on the conflict layer, Chad is the adjacent-system story: where displacement, aid access, and Sahel politics turn a war into a regional stress test.",
        "angle": "The neighboring-country effects of a major conflict.",
        "freshness": "Conflict spillover",
        "place": "Adre / N'Djamena, Chad",
        "country": "Chad",
        "region": "Central Africa",
        "category": "Conflict spillover",
        "lat": 12.1348,
        "lon": 15.0557,
        "importance": 0.71,
        "overlap": [{"type": "ongoing-conflict", "label": "Sudan war"}],
        "sources": [
            {
                "title": "Chad-Sudan border monitoring query",
                "url": "https://reliefweb.int/country/tcd",
            }
        ],
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


def source_from_article(article: dict) -> dict:
    domain = article.get("domain") or "GDELT"
    title = " ".join(str(article.get("title") or "").split()) or f"Recent coverage from {domain}"
    return {
        "title": title,
        "url": article.get("url") or "",
    }


def build_pick(config: dict, articles: list[dict]) -> dict:
    sources = [source_from_article(article) for article in articles[:2]]
    if not sources:
        sources = config.get("sources", [])
    return {
        "id": f"{config['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "title": sources[0]["title"] if articles and sources else config["fallbackTitle"],
        "summary": config["summary"],
        "whyItMatters": config["whyItMatters"],
        "angle": config["angle"],
        "freshness": config["freshness"],
        "lat": config["lat"],
        "lon": config["lon"],
        "place": config["place"],
        "country": config["country"],
        "region": config["region"],
        "category": config["category"],
        "importance": config["importance"],
        "confidence": 0.78 if articles else 0.66,
        "overlap": config.get("overlap", []),
        "sources": sources,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate cached underlooked AI Picks for the globe.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum picks to write.")
    parser.add_argument("--per-query", type=int, default=3, help="Articles to inspect per watchlist query.")
    parser.add_argument("--window-hours", type=int, default=48, help="GDELT lookback window.")
    parser.add_argument("--delay-seconds", type=float, default=6.0, help="Delay between GDELT queries.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    picks = []
    for index, config in enumerate(UNDERLOOKED_STORY_DESK):
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
        "provider": "underlooked-story-desk",
        "windowHours": args.window_hours,
        "selectionPrinciple": "International stories with cross-border stakes that are easy to miss, avoiding obvious week-long headline cycles unless there is a fresh, specific angle.",
        "picks": picks[: args.limit],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['picks'])} AI picks to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
