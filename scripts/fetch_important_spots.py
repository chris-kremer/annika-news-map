#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
OUTPUT_PATH = ROOT / "data" / "generated" / "important_spots.json"
THE_NEWS_ENDPOINT = "https://api.thenewsapi.com/v1/news/top"

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
    },
    {
        "id": "uae-opec",
        "label": "Abu Dhabi / OPEC",
        "lat": 24.45,
        "lon": 54.38,
        "kind": "energy",
        "search": '(UAE OR "United Arab Emirates" OR Abu Dhabi) AND (OPEC OR oil output OR quotas)',
        "locale": "",
        "language": "en,ar",
        "fallbackTitle": "Energy policy moves in the Gulf",
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
    },
    {
        "id": "sahel",
        "label": "Sahel Belt",
        "lat": 15.0,
        "lon": -0.5,
        "kind": "security",
        "search": '(Sahel OR Mali OR Niger OR Burkina Faso) AND (insurgency OR junta OR attacks OR coup)',
        "locale": "",
        "language": "en,fr",
        "fallbackTitle": "Instability across the Sahel belt",
    },
    {
        "id": "sudan",
        "label": "Sudan / Khartoum",
        "lat": 15.57,
        "lon": 32.53,
        "kind": "conflict",
        "search": '(Sudan OR Khartoum OR Darfur) AND (war OR talks OR RSF OR army)',
        "locale": "",
        "language": "en,ar",
        "fallbackTitle": "War and negotiations in Sudan",
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
    },
    {
        "id": "eastern-drc",
        "label": "Eastern DRC",
        "lat": -1.68,
        "lon": 29.23,
        "kind": "minerals",
        "search": '("Democratic Republic of Congo" OR DRC OR Goma) AND (M23 OR cobalt OR mines OR fighting)',
        "locale": "",
        "language": "en,fr",
        "fallbackTitle": "Conflict and critical minerals in eastern DRC",
    },
]

SPOT_CONFIG_BY_ID = {config["id"]: config for config in SPOT_CONFIGS}


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
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
    result = subprocess.run(
        ["curl", "-sfL", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"curl failed for {url}")
    return json.loads(result.stdout)


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


def build_spot_briefing(config: dict, articles: list[dict], limit: int = 5) -> dict:
    deduped = dedupe_articles(articles)[:limit]
    for article in deduped:
        article.pop("_published_at", None)

    if not deduped:
        deduped = [
            {
                "source": "System",
                "time": "Now",
                "title": config["fallbackTitle"],
                "summary": "No recent live stories matched this important-spot query in the current pass.",
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
        "stories": deduped,
    }


def normalize_spot(config: dict, article: dict | None) -> dict:
    if article:
        return {
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
        }
    return {
        "id": config["id"],
        "label": config["label"],
        "lat": config["lat"],
        "lon": config["lon"],
        "kind": config["kind"],
        "title": config["fallbackTitle"],
        "summary": "No live article matched this spot in the current pass.",
        "url": "",
        "time": "Recent",
        "source": "Fallback",
    }


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
        spots.append(normalize_spot(config, article))

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
