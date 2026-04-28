#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
MAP_PATH = ROOT / "data" / "countries-110m.json"
OUTPUT_PATH = ROOT / "data" / "generated" / "briefings.json"

THE_NEWS_ENDPOINT = "https://api.thenewsapi.com/v1/news/top"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

COUNTRY_OVERRIDES = {
    "United States of America": {
        "name": "United States",
        "locale": "us",
        "language": "en",
        "search": '"United States"',
    },
    "Germany": {"locale": "de", "language": "de,en", "search": '"Germany"'},
    "Brazil": {"locale": "br", "language": "pt,en", "search": '"Brazil"'},
    "Japan": {"locale": "jp", "language": "ja,en", "search": '"Japan"'},
    "India": {"locale": "in", "language": "en", "search": '"India"'},
    "Nigeria": {"locale": "ng", "language": "en", "search": '"Nigeria"'},
    "Ukraine": {"language": "uk,en", "search": '"Ukraine"'},
}


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
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(result.stdout.strip() or f"Invalid JSON from {url}") from error


def get_country_names() -> list[str]:
    world = json.loads(MAP_PATH.read_text())
    geometries = world["objects"]["countries"]["geometries"]
    names = [geometry["properties"]["name"] for geometry in geometries]
    return sorted(dict.fromkeys(names))


def get_country_config(country_name: str) -> dict[str, str]:
    config = COUNTRY_OVERRIDES.get(country_name, {})
    return {
        "map_name": country_name,
        "display_name": config.get("name", country_name),
        "search": config.get("search", f'"{country_name}"'),
        "locale": config.get("locale", ""),
        "language": config.get("language", ""),
    }


def format_story_date(raw_value: str) -> str:
    if not raw_value:
        return "Recent"
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        return parsed.strftime("%b %-d")
    except ValueError:
        try:
            parsed = datetime.strptime(raw_value[:8], "%Y%m%d")
            return parsed.strftime("%b %-d")
        except ValueError:
            return "Recent"


def normalize_thenews_article(article: dict) -> dict:
    summary = article.get("description") or article.get("snippet") or "No summary available."
    tags = article.get("categories") or ["general"]
    return {
        "source": "The News API",
        "time": format_story_date(article.get("published_at", "")),
        "title": article.get("title", "Untitled article"),
        "summary": summary,
        "tags": tags[:3],
        "url": article.get("url"),
        "_published_at": article.get("published_at", ""),
    }


def normalize_gdelt_article(article: dict) -> dict:
    summary = f"Matched by GDELT from {article.get('domain', 'news coverage')}."
    source = article.get("domain") or "GDELT"
    tags = [article.get("sourcecountry", "Global"), article.get("language", "Unknown")]
    return {
        "source": source,
        "time": format_story_date(article.get("seendate", "")),
        "title": article.get("title", "Untitled article"),
        "summary": summary,
        "tags": [tag for tag in tags if tag][:3],
        "url": article.get("url"),
        "_published_at": article.get("seendate", ""),
    }


def dedupe_articles(articles: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for article in articles:
        key = (article.get("url") or article.get("title", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    deduped.sort(key=lambda item: item.get("_published_at", ""), reverse=True)
    return deduped


def fetch_thenews_articles(config: dict[str, str], api_token: str, limit: int) -> list[dict]:
    params = {
        "api_token": api_token,
        "search": config["search"],
        "search_fields": "title,description,keywords",
        "published_after": (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d"),
        "sort": "published_at",
        "limit": str(limit),
    }
    if config["locale"]:
        params["locale"] = config["locale"]
    if config["language"]:
        params["language"] = config["language"]

    url = f"{THE_NEWS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = curl_json(url)
    return [normalize_thenews_article(article) for article in payload.get("data", [])]


def fetch_gdelt_articles(config: dict[str, str], limit: int) -> list[dict]:
    params = {
        "query": config["search"],
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(limit),
        "timespan": "3days",
    }
    url = f"{GDELT_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = curl_json(url)
    articles = payload.get("articles", [])
    return [normalize_gdelt_article(article) for article in articles]


def build_tagline(country_name: str, story_count: int) -> str:
    if story_count == 0:
        return f"No live stories were found for {country_name} in this pass."
    if story_count == 1:
        return f"Live briefing compiled from 1 recent story about {country_name}."
    return f"Live briefing compiled from {story_count} recent stories about {country_name}."


def build_country_briefing(
    config: dict[str, str],
    thenews_articles: list[dict],
    gdelt_articles: list[dict],
    limit: int,
) -> dict:
    merged = dedupe_articles(thenews_articles + gdelt_articles)[:limit]
    providers = []
    if thenews_articles:
        providers.append("The News API")
    if gdelt_articles:
        providers.append("GDELT")
    if not providers:
        providers.append("No providers")

    for article in merged:
        article.pop("_published_at", None)

    return {
        "name": config["display_name"],
        "updated": f"Updated {datetime.now(timezone.utc).strftime('%B %-d, %Y')}",
        "tagline": build_tagline(config["display_name"], len(merged)),
        "sourceNote": "Live briefing from " + " + ".join(providers) + ".",
        "stories": merged,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch live country briefings.")
    parser.add_argument(
        "--countries",
        help="Comma-separated list of country names to refresh. Defaults to all map countries.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of stories to keep per country.",
    )
    parser.add_argument(
        "--gdelt-countries",
        default="",
        help="Comma-separated list of countries to supplement with GDELT.",
    )
    parser.add_argument(
        "--gdelt-delay-seconds",
        type=float,
        default=6.0,
        help="Delay between GDELT requests.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = load_env()
    api_token = env.get("THE_NEWS_API_TOKEN")
    if not api_token:
        print("Missing THE_NEWS_API_TOKEN in .env.local", file=sys.stderr)
        return 1

    all_countries = get_country_names()
    if args.countries:
        requested = [name.strip() for name in args.countries.split(",") if name.strip()]
        countries = [name for name in requested if name in all_countries]
    else:
        countries = all_countries

    gdelt_targets = {
        name.strip() for name in args.gdelt_countries.split(",") if name.strip()
    }

    output = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "countries": {},
    }

    for index, country_name in enumerate(countries):
        config = get_country_config(country_name)
        thenews_articles = []
        gdelt_articles = []

        try:
            thenews_articles = fetch_thenews_articles(config, api_token, args.limit)
        except Exception as exc:
            print(f"The News API failed for {country_name}: {exc}", file=sys.stderr)

        if country_name in gdelt_targets:
            if index > 0:
                time.sleep(args.gdelt_delay_seconds)
            try:
                gdelt_articles = fetch_gdelt_articles(config, args.limit)
            except Exception as exc:
                print(f"GDELT failed for {country_name}: {exc}", file=sys.stderr)

        output["countries"][country_name] = build_country_briefing(
            config,
            thenews_articles,
            gdelt_articles,
            args.limit,
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(output['countries'])} country briefings to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
