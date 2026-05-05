#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_briefings


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
OUTPUT_PATH = ROOT / "data" / "generated" / "ai_picks.json"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5-nano"
SELECTION_PRINCIPLE = "International stories with cross-border stakes that are easy to miss, avoiding obvious week-long headline cycles unless there is a fresh, specific angle."

try:
    import certifi
except ImportError:
    certifi = None

SSL_CONTEXT = (
    ssl.create_default_context(cafile=certifi.where())
    if certifi
    else ssl.create_default_context()
)

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


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


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


def openai_text_from_response(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def clean_model_pick(raw_pick: dict, fallback_by_id: dict[str, dict]) -> dict | None:
    raw_id = str(raw_pick.get("id", "")).strip()
    fallback = fallback_by_id.get(raw_id)
    if not fallback:
        return None

    cleaned = dict(fallback)
    for key in ["title", "summary", "whyItMatters", "angle", "freshness", "category"]:
        value = str(raw_pick.get(key, "")).strip()
        if value:
            cleaned[key] = value

    for key in ["importance", "confidence"]:
        try:
            value = float(raw_pick.get(key))
        except (TypeError, ValueError):
            continue
        cleaned[key] = max(0.0, min(1.0, value))

    sources = raw_pick.get("sources")
    if isinstance(sources, list) and sources:
        cleaned_sources = []
        for source in sources[:3]:
            if not isinstance(source, dict):
                continue
            title = str(source.get("title", "")).strip()
            url = str(source.get("url", "")).strip()
            if title or url:
                cleaned_sources.append({"title": title or cleaned["title"], "url": url})
        if cleaned_sources:
            cleaned["sources"] = cleaned_sources
    return cleaned


def curate_with_openai(picks: list[dict], limit: int, env: dict[str, str]) -> list[dict]:
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return picks

    model = env.get("OPENAI_AI_PICKS_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    prompt_payload = {
        "selectionPrinciple": SELECTION_PRINCIPLE,
        "requirements": [
            "Return the most interesting underlooked international picks, ranked by importance.",
            "Prefer fresh specific angles over generic week-long headline cycles.",
            "Do not invent facts, places, URLs, or sources. Use only the candidate data.",
            "If a pick overlaps an ongoing conflict or key area, preserve its overlap field.",
            "Keep coordinates unchanged so markers remain correctly placed on the globe.",
        ],
        "outputShape": {
            "picks": [
                {
                    "id": "candidate id",
                    "title": "specific, concise title",
                    "summary": "one sentence",
                    "whyItMatters": "one sentence on cross-border stakes",
                    "angle": "fresh editorial angle",
                    "freshness": "short label",
                    "category": "short category",
                    "importance": "0.0-1.0",
                    "confidence": "0.0-1.0",
                    "sources": [{"title": "source title", "url": "source URL"}],
                }
            ]
        },
        "candidates": picks,
        "limit": limit,
    }
    body = {
        "model": model,
        "instructions": "You are the Pumpkin News assignment editor. Return valid JSON only.",
        "input": json.dumps(prompt_payload, ensure_ascii=False),
        "max_output_tokens": 6000,
        "reasoning": {"effort": "minimal"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ai_picks",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "whyItMatters": {"type": "string"},
                                    "angle": {"type": "string"},
                                    "freshness": {"type": "string"},
                                    "category": {"type": "string"},
                                    "importance": {"type": "number"},
                                    "confidence": {"type": "number"},
                                    "sources": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "title": {"type": "string"},
                                                "url": {"type": "string"},
                                            },
                                            "required": ["title", "url"],
                                        },
                                    },
                                },
                                "required": [
                                    "id",
                                    "title",
                                    "summary",
                                    "whyItMatters",
                                    "angle",
                                    "freshness",
                                    "category",
                                    "importance",
                                    "confidence",
                                    "sources",
                                ],
                            },
                        }
                    },
                    "required": ["picks"],
                },
            }
        },
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        payload = json.loads(response.read().decode("utf-8"))

    model_payload = extract_json_object(openai_text_from_response(payload))
    raw_picks = model_payload.get("picks", [])
    if not isinstance(raw_picks, list):
        raise RuntimeError("OpenAI response did not include a picks array")

    fallback_by_id = {pick["id"]: pick for pick in picks}
    curated = []
    seen = set()
    for raw_pick in raw_picks:
        if not isinstance(raw_pick, dict):
            continue
        cleaned = clean_model_pick(raw_pick, fallback_by_id)
        if not cleaned or cleaned["id"] in seen:
            continue
        seen.add(cleaned["id"])
        curated.append(cleaned)

    if not curated:
        raise RuntimeError("OpenAI response did not return usable picks")
    return curated[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate cached underlooked AI Picks for the globe.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum picks to write.")
    parser.add_argument("--per-query", type=int, default=3, help="Articles to inspect per watchlist query.")
    parser.add_argument("--window-hours", type=int, default=48, help="GDELT lookback window.")
    parser.add_argument("--delay-seconds", type=float, default=6.0, help="Delay between GDELT queries.")
    parser.add_argument("--skip-openai", action="store_true", help="Use seeded/GDELT picks without OpenAI curation.")
    parser.add_argument("--skip-gdelt", action="store_true", help="Use seeded candidates without GDELT enrichment.")
    return parser.parse_args()


def build_payload(args: argparse.Namespace | None = None) -> dict:
    if args is None:
        args = parse_args()
    env = load_env()
    picks = []
    for index, config in enumerate(UNDERLOOKED_STORY_DESK):
        if index and not args.skip_gdelt:
            time.sleep(args.delay_seconds)
        articles = []
        if not args.skip_gdelt:
            try:
                articles = fetch_gdelt(config["query"], args.per_query, args.window_hours)
            except Exception as error:
                print(f"warning: {config['id']} query failed: {error}", file=sys.stderr)
        picks.append(build_pick(config, articles))

    picks.sort(key=lambda pick: pick["importance"], reverse=True)
    provider = "underlooked-story-desk"
    if not args.skip_openai:
        try:
            picks = curate_with_openai(picks, args.limit, env)
            provider = f"openai:{env.get('OPENAI_AI_PICKS_MODEL', DEFAULT_OPENAI_MODEL)}"
        except Exception as error:
            print(f"warning: OpenAI curation failed: {error}", file=sys.stderr)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "windowHours": args.window_hours,
        "selectionPrinciple": SELECTION_PRINCIPLE,
        "picks": picks[: args.limit],
    }


def main() -> int:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['picks'])} AI picks to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
