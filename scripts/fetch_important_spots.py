#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
OUTPUT_PATH = ROOT / "data" / "generated" / "important_spots.json"
THE_NEWS_ENDPOINT = "https://api.thenewsapi.com/v1/news/top"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

try:
    import certifi
except ImportError:
    certifi = None

SSL_CONTEXT = (
    ssl.create_default_context(cafile=certifi.where())
    if certifi
    else ssl.create_default_context()
)
REQUEST_HEADERS = {
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "User-Agent": "annika-news-map/1.0",
}

SPOT_CONFIGS = [
    {
        "id": "hormuz",
        "label": "Strait of Hormuz",
        "lat": 26.57,
        "lon": 56.25,
        "kind": "chokepoint",
        "search": '("Strait of Hormuz" OR Hormuz) AND (shipping OR oil OR closure OR tanker)',
        "locale": "",
        "language": "en",
        "fallbackTitle": "Shipping and energy risk around Hormuz",
        "fallbackSummary": "Hormuz remains the energy chokepoint to watch when Gulf tensions touch shipping, insurance, or oil flows.",
        "fallbackStories": [
            {
                "source": "MarketScreener",
                "time": "Apr 28",
                "title": "Only five ships pass through Strait of Hormuz in 24 hours",
                "summary": "A sparse-traffic datapoint keeps Hormuz on the key-area layer because small changes in tanker movement can become an oil-price and insurance story quickly.",
                "tags": ["Chokepoint", "Shipping", "Energy"],
                "url": "https://www.marketscreener.com/news/only-five-ships-pass-through-strait-of-hormuz-in-24-hours-ce7f59dfdb8ff320",
            }
        ],
        "marketUrl": "https://polymarket.com/event/strait-of-hormuz-traffic-returns-to-normal-by-end-of-june",
        "marketFallback": {
            "title": "Strait of Hormuz traffic returns to normal by end of June?",
            "url": "https://polymarket.com/event/strait-of-hormuz-traffic-returns-to-normal-by-end-of-june",
            "yesProbability": "60%",
            "volume": "$816,715",
            "resolveDate": "2026-06-30",
            "updatedLabel": "Apr 28, 2026",
            "note": "Prediction-market pricing from Polymarket. This is a market signal, not a forecast guarantee.",
        },
    },
    {
        "id": "taiwan-strait",
        "label": "Taiwan Strait",
        "lat": 24.0,
        "lon": 119.4,
        "kind": "military",
        "search": '("Taiwan Strait" OR Taiwan) AND (drills OR blockade OR military OR naval)',
        "locale": "",
        "language": "en,zh",
        "fallbackTitle": "Military signaling around Taiwan",
        "fallbackSummary": "The useful Taiwan Strait signal is not one headline; it is the tempo of drills, patrols, blockade talk, and outside naval responses.",
        "fallbackStories": [
            {
                "source": "Focus Taiwan",
                "time": "Recent",
                "title": "Taiwan Strait remains a military signaling zone",
                "summary": "Keep watching the gap between routine pressure and anything that changes the operational pattern: larger drills, quarantine language, blockade logistics, or unusual US/Japan responses.",
                "tags": ["Military", "Deterrence", "Cross-strait"],
                "url": "https://focustaiwan.tw/cross-strait",
            }
        ],
        "marketUrl": "https://polymarket.com/event/will-china-invade-taiwan-by-december-31-2027",
        "marketFallback": {
            "title": "Will China invade Taiwan by December 31, 2027?",
            "url": "https://polymarket.com/event/will-china-invade-taiwan-by-december-31-2027",
            "yesProbability": "18%",
            "volume": "$364,909",
            "resolveDate": "2027-12-31",
            "updatedLabel": "Apr 28, 2026",
            "note": "Prediction-market pricing from Polymarket. This is a market signal, not a forecast guarantee.",
        },
    },
    {
        "id": "south-china-sea",
        "label": "South China Sea",
        "lat": 12.0,
        "lon": 114.5,
        "kind": "maritime",
        "search": '("South China Sea" OR Scarborough OR Spratly) AND (ship OR coast guard OR ramming OR navy)',
        "locale": "",
        "language": "en,zh",
        "fallbackTitle": "Maritime pressure in the South China Sea",
        "fallbackSummary": "This layer tracks coast-guard and maritime-militia friction where small collisions or water-cannon incidents can become diplomatic crises.",
        "fallbackStories": [
            {
                "source": "AMTI",
                "time": "Recent",
                "title": "South China Sea pressure centers on coast-guard encounters and shoal access",
                "summary": "The highest-signal updates are usually not declarations; they are repeated encounters near Scarborough Shoal, Second Thomas Shoal, or Spratly features.",
                "tags": ["Maritime", "China", "Philippines"],
                "url": "https://amti.csis.org/",
            }
        ],
    },
    {
        "id": "red-sea",
        "label": "Red Sea / Bab el-Mandeb",
        "lat": 13.3,
        "lon": 43.2,
        "kind": "shipping",
        "search": '("Red Sea" OR "Bab el-Mandeb") AND (shipping OR attacks OR missiles OR Houthis)',
        "locale": "",
        "language": "en,ar",
        "fallbackTitle": "Shipping risk in the Red Sea corridor",
        "fallbackSummary": "Red Sea risk is about whether attacks, insurance costs, and rerouting remain abnormal enough to keep freight away from Suez.",
        "fallbackStories": [
            {
                "source": "Reuters",
                "time": "Recent",
                "title": "Red Sea shipping remains sensitive to Houthi attack risk",
                "summary": "The key-area question is whether carriers treat the route as normal again or keep paying the time and fuel penalty to avoid Bab el-Mandeb.",
                "tags": ["Shipping", "Houthis", "Insurance"],
                "url": "https://www.reuters.com/world/middle-east/",
            }
        ],
    },
    {
        "id": "suez",
        "label": "Suez Canal",
        "lat": 30.5,
        "lon": 32.35,
        "kind": "chokepoint",
        "search": '("Suez Canal" OR Suez) AND (shipping OR transit OR disruption OR rerouting)',
        "locale": "",
        "language": "en,ar",
        "fallbackTitle": "Canal transit and rerouting pressure",
        "fallbackSummary": "Suez is the downstream indicator for Red Sea risk: if ships keep rerouting, canal revenue, delivery times, and freight pricing show the pressure.",
        "fallbackStories": [
            {
                "source": "Suez Canal Authority",
                "time": "Recent",
                "title": "Suez transit is the practical readout for Red Sea disruption",
                "summary": "Watch canal traffic and revenue rather than rhetoric; sustained diversions around the Cape are the clearest signal that the shipping corridor is not back to normal.",
                "tags": ["Chokepoint", "Trade", "Revenue"],
                "url": "https://www.suezcanal.gov.eg/",
            }
        ],
    },
    {
        "id": "cuba",
        "label": "Cuba",
        "lat": 23.13,
        "lon": -82.35,
        "kind": "flashpoint",
        "search": '(Cuba OR Havana) AND (United States OR sanctions OR military OR blackout OR protests)',
        "locale": "",
        "language": "en,es",
        "fallbackTitle": "US-Cuba tension and internal pressure",
        "fallbackSummary": "Cuba is tracked for the overlap between domestic strain, power outages, sanctions politics, migration, and US security rhetoric.",
        "fallbackStories": [
            {
                "source": "AP",
                "time": "Recent",
                "title": "Cuba pressure story combines outages, sanctions, migration, and US politics",
                "summary": "The key-area value is context: a Cuba headline can be economic, humanitarian, migration-related, or military-rhetorical, but those pieces reinforce each other.",
                "tags": ["Flashpoint", "Sanctions", "Migration"],
                "url": "https://apnews.com/hub/cuba",
            }
        ],
        "marketUrl": "https://polymarket.com/event/us-strike-on-cuba-by",
        "marketFallback": {
            "title": "US military action against Cuba by December 31, 2026?",
            "url": "https://polymarket.com/event/us-strike-on-cuba-by",
            "yesProbability": "40%",
            "volume": "$3,100,806",
            "resolveDate": "2026-12-31",
            "updatedLabel": "Apr 15, 2026",
            "note": 'Prediction-market pricing from Polymarket. Current leading branch is "December 31, 2026." This is a market signal, not a forecast guarantee.',
        },
    },
    {
        "id": "kashmir",
        "label": "Kashmir",
        "lat": 34.08,
        "lon": 74.79,
        "kind": "border",
        "search": '(Kashmir OR "Line of Control") AND (India OR Pakistan OR clashes OR militants)',
        "locale": "",
        "language": "en,hi,ur",
        "fallbackTitle": "India-Pakistan tension around Kashmir",
        "fallbackSummary": "Kashmir is a key-area seed because local militancy or border clashes can quickly become a nuclear-neighbor crisis-management story.",
        "fallbackStories": [
            {
                "source": "Al Jazeera",
                "time": "Recent",
                "title": "Kashmir remains the India-Pakistan flashpoint to watch for escalation",
                "summary": "The signal to watch is not only attacks or arrests, but whether either side shifts troop posture, air restrictions, or diplomatic language after an incident.",
                "tags": ["Border", "India", "Pakistan"],
                "url": "https://www.aljazeera.com/where/kashmir/",
            }
        ],
    },
]

SPOT_CONFIG_BY_ID = {config["id"]: config for config in SPOT_CONFIGS}


def load_env() -> dict[str, str]:
    values: dict[str, str] = dict(os.environ)
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def curl_json(url: str) -> dict:
    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except OSError as error:
        raise RuntimeError(f"request failed for {redact_url(url)}: {error}") from error


def curl_text(url: str) -> str:
    try:
        request = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
            return response.read().decode("utf-8")
    except OSError as error:
        raise RuntimeError(f"request failed for {redact_url(url)}: {error}") from error


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "redacted" if key.lower() in {"api_token", "token", "key"} else value)
        for key, value in params
    ]
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(redacted))
    )


def format_story_date(raw_value: str) -> str:
    if not raw_value:
        return "Recent"
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return parsed.strftime("%b %-d")
    except ValueError:
        return "Recent"


def normalize_thenews_article(article: dict) -> dict:
    summary = article.get("description") or article.get("snippet") or "No summary available."
    tags = article.get("categories") or ["global"]
    return {
        "source": article.get("source") or "The News API",
        "time": format_story_date(article.get("published_at", "")),
        "title": article.get("title") or "Untitled article",
        "summary": summary,
        "tags": tags[:3],
        "url": article.get("url") or "",
        "_published_at": article.get("published_at", ""),
    }


def normalize_gdelt_article(article: dict) -> dict:
    return {
        "source": article.get("domain") or "GDELT",
        "time": format_story_date(article.get("seendate", "")),
        "title": article.get("title") or "Untitled article",
        "summary": f"Matched by GDELT from {article.get('domain', 'global coverage')}.",
        "tags": [tag for tag in [article.get("sourcecountry"), article.get("language")] if tag][:3],
        "url": article.get("url") or "",
        "_published_at": article.get("seendate", ""),
    }


def dedupe_articles(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for article in articles:
        key = (article.get("url") or article.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    deduped.sort(key=lambda item: item.get("_published_at", ""), reverse=True)
    return deduped


def get_spot_ids() -> list[str]:
    return sorted(SPOT_CONFIG_BY_ID)


def get_spot_config(spot_id: str) -> dict:
    config = SPOT_CONFIG_BY_ID.get(spot_id)
    if not config:
        raise KeyError(f"Unknown spot: {spot_id}")
    return config


def format_kind(kind: str) -> str:
    return kind.replace("-", " ").title()


def fetch_spot_articles(config: dict, api_token: str, limit: int) -> list[dict]:
    params = {
        "api_token": api_token,
        "search": config["search"],
        "search_fields": "title,description,keywords",
        "published_after": (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d"),
        "sort": "published_at",
        "limit": str(limit),
    }
    if config.get("locale"):
        params["locale"] = config["locale"]
    if config.get("language"):
        params["language"] = config["language"]

    url = f"{THE_NEWS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = curl_json(url)
    articles = payload.get("data") or []
    return [normalize_thenews_article(article) for article in articles]


def fetch_top_story(config: dict, api_token: str) -> dict | None:
    articles = fetch_spot_articles(config, api_token, limit=1)
    return articles[0] if articles else None


def fetch_gdelt_articles(config: dict, limit: int) -> list[dict]:
    params = {
        "query": config["search"],
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(limit),
        "timespan": "5days",
    }
    url = f"{GDELT_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = curl_json(url)
    return [normalize_gdelt_article(article) for article in payload.get("articles", [])]


def fetch_polymarket_card(url: str, fallback_card: dict | None = None) -> dict:
    try:
        html = curl_text(url)
    except Exception:
        if fallback_card:
            return dict(fallback_card)
        raise

    title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
    volume_match = re.search(r"\$([\d,]+) has traded on", html)
    prob_match = re.search(r"current crowd-sourced probability is (\d+(?:\.\d+)?)% for \\\\\"Yes", html)
    if not prob_match:
        prob_match = re.search(r"current probability for .*? is (\d+(?:\.\d+)?)% for \\\\\"Yes", html)
    if not prob_match:
        prob_match = re.search(r"price of (\d+(?:\.\d+)?)¢ for .*? means traders collectively believe there is a (\d+(?:\.\d+)?)% chance", html)
    end_match = re.search(r'"endDate":"([^"]+)"', html)
    updated_match = re.search(r"as of ([A-Za-z]+ \d{1,2}, \d{4})", html)

    probability = None
    if prob_match:
        if len(prob_match.groups()) >= 2:
            probability = prob_match.group(2)
        else:
            probability = prob_match.group(1)

    resolve_date = None
    if end_match:
        resolve_date = end_match.group(1)[:10]

    return {
        "title": title_match.group(1) if title_match else "Polymarket market",
        "url": url,
        "yesProbability": f"{probability}%" if probability else "Unavailable",
        "volume": f"${volume_match.group(1)}" if volume_match else "Unavailable",
        "resolveDate": resolve_date or "Unavailable",
        "updatedLabel": updated_match.group(1) if updated_match else "Today",
        "note": "Prediction-market pricing from Polymarket. This is a market signal, not a forecast guarantee.",
    }


def build_spot_briefing(config: dict, thenews_articles: list[dict], gdelt_articles: list[dict], limit: int = 5) -> dict:
    deduped = dedupe_articles(thenews_articles + gdelt_articles)[:limit]
    for article in deduped:
        article.pop("_published_at", None)

    if not deduped:
        deduped = [dict(story) for story in config.get("fallbackStories", [])] or [
            {
                "source": "System",
                "time": "Now",
                "title": config["fallbackTitle"],
                "summary": config.get("fallbackSummary")
                or "No recent live stories matched this important-spot query in the current pass.",
                "tags": [format_kind(config["kind"]), "Query", "Sparse"],
                "url": "",
            }
        ]

    return {
        "id": config["id"],
        "name": config["label"],
        "label": config["label"],
        "kind": format_kind(config["kind"]),
        "windowDays": 5,
        "sourceNote": " + ".join(
            [
                source
                for source, has_items in [("The News API", bool(thenews_articles)), ("GDELT", bool(gdelt_articles))]
                if has_items
            ]
        )
        or "Fallback",
        "stories": deduped,
    }


def normalize_spot(config: dict, article: dict | None) -> dict:
    market_card = config.get("marketFallback")
    if article:
        spot = {
            "id": config["id"],
            "label": config["label"],
            "lat": config["lat"],
            "lon": config["lon"],
            "kind": config["kind"],
            "title": article.get("title") or config["fallbackTitle"],
            "summary": article.get("summary") or config["fallbackTitle"],
            "url": article.get("url") or "",
            "time": article.get("time") or "Recent",
            "source": article.get("source") or "The News API",
            "stories": [article],
        }
    else:
        spot = {
            "id": config["id"],
            "label": config["label"],
            "lat": config["lat"],
            "lon": config["lon"],
            "kind": config["kind"],
            "title": config["fallbackTitle"],
            "summary": config.get("fallbackSummary") or "No live article matched this spot in the current pass.",
            "url": "",
            "time": "Recent",
            "source": "Editorial seed",
            "stories": [dict(story) for story in config.get("fallbackStories", [])],
        }

    if market_card:
        spot["marketCard"] = dict(market_card)
    return spot


def normalize_spot_briefing(config: dict) -> dict:
    briefing = {
        "id": config["id"],
        "name": config["label"],
        "label": config["label"],
        "kind": format_kind(config["kind"]),
        "windowDays": 5,
        "sourceNote": "Editorial seed",
        "stories": [dict(story) for story in config.get("fallbackStories", [])],
    }
    if config.get("marketFallback"):
        briefing["marketCard"] = dict(config["marketFallback"])
    return briefing


def build_payload() -> dict:
    env = load_env()
    api_token = env.get("THE_NEWS_API_TOKEN")
    spots: list[dict] = []

    for config in SPOT_CONFIGS:
        article = None
        if api_token:
            try:
                article = fetch_top_story(config, api_token)
            except Exception:
                article = None
        if not article:
            try:
                gdelt_articles = fetch_gdelt_articles(config, limit=1)
                article = gdelt_articles[0] if gdelt_articles else None
            except Exception:
                article = None
        spot = normalize_spot(config, article)
        spot["briefing"] = normalize_spot_briefing(config)
        spots.append(spot)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "the-news-api" if api_token else "fallback",
        "windowDays": 5,
        "spots": spots,
    }


def main() -> int:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['spots'])} important spots to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
