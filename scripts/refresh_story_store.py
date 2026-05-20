#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import fetch_ai_picks
import fetch_briefings
import story_store


ROOT = Path(__file__).resolve().parents[1]
COUNTRY_TTL = timedelta(hours=24)
TOP_STORIES_TTL = timedelta(hours=6)
COUNTRY_HISTORY_TTL = timedelta(days=90)


def stale_after(ttl: timedelta) -> str:
    return (datetime.now(timezone.utc) + ttl).isoformat()


def clean_country_history_summary(value: Any, country_name: str) -> str:
    summary = str(value or "").strip()
    normalized = re.sub(r"\s+", " ", summary).strip(" ;")
    lowered = normalized.lower()
    placeholder_patterns = [
        "five-sentence recent history briefing",
        "recent history briefing for",
        "last ~10 years",
        "last 10 years",
    ]
    if not normalized:
        raise RuntimeError("OpenAI history response did not include a summary")
    if any(pattern in lowered for pattern in placeholder_patterns) and len(normalized) < 160:
        raise RuntimeError(f"OpenAI history response returned a placeholder summary for {country_name}")
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", normalized))
    semicolon_count = normalized.count(";")
    if sentence_count < 3 and semicolon_count < 3:
        raise RuntimeError(f"OpenAI history response was too short for {country_name}")
    return normalized


def openai_country_briefing(
    config: dict[str, str],
    articles: list[dict[str, Any]],
    env: dict[str, str],
    limit: int,
) -> dict[str, Any] | None:
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key or (not articles and env.get("OPENAI_COUNTRY_WEB_SEARCH", "1") == "0"):
        return None

    model = env.get("OPENAI_COUNTRY_BRIEFING_MODEL", fetch_ai_picks.DEFAULT_OPENAI_MODEL).strip()
    use_web_search = env.get("OPENAI_COUNTRY_WEB_SEARCH", "1") != "0"
    source_mode = "fresh web search plus supplied provider candidates" if use_web_search else "supplied provider candidates"
    body = {
        "model": model or fetch_ai_picks.DEFAULT_OPENAI_MODEL,
        "instructions": "You are a careful news editor for a map-first briefing app. Return valid JSON only.",
        "input": json.dumps(
            {
                "country": config["display_name"],
                "task": (
                    f"Create a current English country situation briefing from {source_mode}. "
                    "This should answer the user question: 'Tell me what is currently going on in this country.'"
                ),
                "searchPlan": [
                    f"{config['display_name']} current political situation 2026",
                    f"{config['display_name']} economy security civil rights current news 2026",
                    f"{config['display_name']} tourism energy infrastructure current developments 2026",
                ],
                "requirements": [
                    "Do not rely on training data for current claims.",
                    "When web search is available, you must use it before writing.",
                    "Do not say more sources are needed; search for them.",
                    "Actively search for current country-specific developments and durable context before writing.",
                    "Use only facts and URLs from supplied articles or web-search results.",
                    "Return every user-facing field in English, including tagline, story titles, story summaries, sources, and tags.",
                    "Translate non-English source material into natural English; do not copy non-English headlines or summaries into the output.",
                    "Drop articles that are irrelevant to the country.",
                    "Write 3 to 5 briefing sections, not a raw list of headlines.",
                    "Cover the current political leadership/backdrop, major security or rights issues, economic or development direction, and the most important recent movement.",
                    "Include concrete numbers or time spans only when supported by a source.",
                    "Do not lead with GDP or growth figures unless they are central to the country's current story.",
                    "Keep economic data to at most one section; prioritize readable political and social context.",
                    "Prefer country-specific sources, international wires, official statistics, international organizations, and reputable explainers.",
                    "Each non-system section should cite one source URL used for that section.",
                    "Do not invent sources or facts.",
                ],
                "providerCandidates": articles[: max(limit * 2, limit)],
                "limit": limit,
            },
            ensure_ascii=False,
        ),
        "max_output_tokens": 5000,
        "reasoning": {"effort": "low" if use_web_search else "minimal"},
        "tools": [{"type": "web_search"}] if use_web_search else [],
        "tool_choice": "required" if use_web_search else "none",
        "include": ["web_search_call.action.sources"] if use_web_search else [],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "country_briefing",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tagline": {"type": "string"},
                        "stories": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "source": {"type": "string"},
                                    "time": {"type": "string"},
                                    "title": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                    "url": {"type": "string"},
                                },
                                "required": ["source", "time", "title", "summary", "tags", "url"],
                            },
                        },
                    },
                    "required": ["tagline", "stories"],
                },
            }
        },
    }
    request = urllib.request.Request(
        fetch_ai_picks.OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=fetch_ai_picks.SSL_CONTEXT) as response:
        payload = json.loads(response.read().decode("utf-8"))

    parsed = fetch_ai_picks.extract_json_object(fetch_ai_picks.openai_text_from_response(payload))
    allowed_urls = {str(article.get("url") or "").strip() for article in articles}
    allowed_urls.update(collect_openai_source_urls(payload))
    stories = sanitize_openai_country_stories(parsed.get("stories", []), allowed_urls, allow_searched_urls=use_web_search)
    if not isinstance(stories, list) or not stories:
        return None
    return {
        "name": config["display_name"],
        "updated": f"Updated {datetime.now(timezone.utc).strftime('%B %-d, %Y')}",
        "tagline": str(parsed.get("tagline") or f"Current situation briefing for {config['display_name']}."),
        "sourceNote": (
            f"OpenAI web-searched briefing from {len(allowed_urls)} source URLs."
            if use_web_search
            else f"OpenAI-edited briefing from {len(articles)} candidate articles."
        ),
        "stories": stories[:limit],
    }


def collect_openai_source_urls(value: Any) -> set[str]:
    urls: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "url" and isinstance(item, str) and item.startswith(("http://", "https://")):
                urls.add(item)
            else:
                urls.update(collect_openai_source_urls(item))
    elif isinstance(value, list):
        for item in value:
            urls.update(collect_openai_source_urls(item))
    return urls


def sanitize_openai_country_stories(
    stories: Any,
    allowed_urls: set[str],
    *,
    allow_searched_urls: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(stories, list):
        return []
    cleaned = []
    for story in stories:
        if not isinstance(story, dict):
            continue
        url = str(story.get("url") or "").strip()
        title = str(story.get("title") or "").strip()
        summary = str(story.get("summary") or "").strip()
        if url and url not in allowed_urls and not is_allowed_searched_url(url, allow_searched_urls):
            url = ""
        if not url and title.lower().startswith(("no ", "no title", "no relevant", "no supplied")):
            cleaned.append(
                {
                    "source": "System",
                    "time": "Now",
                    "title": "No relevant live stories matched this country",
                    "summary": summary or "The fetched provider results did not contain a verifiable country-specific story.",
                    "tags": ["Sparse coverage", "AI reviewed"],
                    "url": "",
                }
            )
            continue
        if not title or not summary:
            continue
        if looks_non_english_text(f"{title} {summary}"):
            continue
        if allow_searched_urls and not url:
            continue
        cleaned.append(
            {
                "source": str(story.get("source") or "Live source"),
                "time": str(story.get("time") or "Recent"),
                "title": title,
                "summary": summary,
                "tags": [str(tag) for tag in story.get("tags", [])[:3]] if isinstance(story.get("tags"), list) else ["general"],
                "url": url,
            }
        )
    return cleaned


def looks_non_english_text(text: str) -> bool:
    lowered = f" {text.lower()} "
    markers = [
        " governo ",
        " congresso ",
        " medidas ",
        " eleitorais ",
        " crescimento ",
        " ministério ",
        " fazenda ",
        " inflação ",
        " cenário ",
        " petróleo ",
        " para ",
        " enquanto ",
        " acuerdo ",
        " gobierno ",
        " congreso ",
        " elecciones ",
    ]
    return sum(1 for marker in markers if marker in lowered) >= 2


def is_allowed_searched_url(url: str, allow_searched_urls: bool) -> bool:
    if not allow_searched_urls:
        return False
    lowered = url.lower()
    if any(char.isspace() for char in url):
        return False
    if not lowered.startswith(("http://", "https://")):
        return False
    return "example." not in lowered


def raw_country_articles(config: dict[str, str], api_token: str, limit: int) -> tuple[list[dict], list[dict]]:
    if not api_token:
        return [], []
    try:
        thenews = fetch_briefings.fetch_thenews_articles(config, api_token, limit=max(limit * 2, limit), window_days=3)
        if not thenews:
            thenews = fetch_briefings.fetch_thenews_articles(config, api_token, limit=max(limit * 2, limit), window_days=14)
    except Exception as error:
        print(f"warning: provider news fetch failed for {config['display_name']}: {error}", flush=True, file=sys.stderr)
        thenews = []
    gdelt = []
    if len(thenews) < 2:
        try:
            gdelt = fetch_briefings.fetch_gdelt_articles(config, limit=limit, window_days=14)
        except Exception as error:
            print(f"warning: GDELT fetch failed for {config['display_name']}: {error}", flush=True, file=sys.stderr)
            gdelt = []
    return thenews, gdelt


def refresh_country(country_name: str, limit: int = 5) -> dict[str, Any]:
    env = fetch_briefings.load_env()
    api_token = env.get("THE_NEWS_API_TOKEN", "").strip()
    if not api_token and not env.get("OPENAI_API_KEY", "").strip():
        raise RuntimeError("Missing THE_NEWS_API_TOKEN")

    config = fetch_briefings.get_country_config(country_name)
    thenews, gdelt = raw_country_articles(config, api_token, limit)
    articles = thenews + gdelt
    briefing = openai_country_briefing(config, articles, env, limit)
    if briefing is None:
        if env.get("OPENAI_API_KEY", "").strip() and env.get("OPENAI_COUNTRY_WEB_SEARCH", "1") != "0":
            briefing = no_relevant_country_briefing(
                config,
                "OpenAI web search did not return a verifiable country-specific story.",
            )
        else:
            briefing = fetch_briefings.build_country_briefing(config, thenews, gdelt, limit)
    briefing["cachedAt"] = datetime.now(timezone.utc).isoformat()
    briefing["cacheStatus"] = "fresh"
    story_store.write_country_briefing(country_name, briefing, stale_after=stale_after(COUNTRY_TTL))
    return briefing


def no_relevant_country_briefing(config: dict[str, str], summary: str) -> dict[str, Any]:
    return {
        "name": config["display_name"],
        "updated": f"Updated {datetime.now(timezone.utc).strftime('%B %-d, %Y')}",
        "tagline": f"No current country-specific stories were verified for {config['display_name']}.",
        "sourceNote": "OpenAI web-searched briefing.",
        "stories": [
            {
                "source": "System",
                "time": "Now",
                "title": "No relevant live stories matched this country",
                "summary": summary,
                "tags": ["Sparse coverage", "AI reviewed"],
                "url": "",
            }
        ],
    }


def refresh_country_history(country_name: str) -> dict[str, Any]:
    env = fetch_briefings.load_env()
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    config = fetch_briefings.get_country_config(country_name)
    model = env.get("OPENAI_COUNTRY_BRIEFING_MODEL", fetch_ai_picks.DEFAULT_OPENAI_MODEL).strip()
    body = {
        "model": model or fetch_ai_picks.DEFAULT_OPENAI_MODEL,
        "instructions": "You write compact, sourced country background briefings. Return valid JSON only.",
        "input": json.dumps(
            {
                "country": config["display_name"],
                "task": "Write a 5-sentence Recent history briefing covering roughly the last 10 years.",
                "requirements": [
                    "Use web search before writing.",
                    "Focus on political trajectory, security, social change, economy/development, and international positioning.",
                    "Keep it readable for a general audience.",
                    "Do not overemphasize GDP or growth figures.",
                    "Use only facts supported by web-search sources.",
                    "The summary field must contain the actual briefing prose, not a title, label, placeholder, or description of the task.",
                    "Return exactly 5 complete factual sentences in one paragraph.",
                    "Do not write phrases like 'Five-sentence recent history briefing' or 'last 10 years' as the summary.",
                ],
            },
            ensure_ascii=False,
        ),
        "max_output_tokens": 1800,
        "reasoning": {"effort": "low"},
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "country_recent_history",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "summary": {"type": "string"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["summary", "sources"],
                },
            }
        },
    }
    request = urllib.request.Request(
        fetch_ai_picks.OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=fetch_ai_picks.SSL_CONTEXT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parsed = fetch_ai_picks.extract_json_object(fetch_ai_picks.openai_text_from_response(payload))
    source_urls = collect_openai_source_urls(payload)
    requested_sources = [
        url for url in parsed.get("sources", [])
        if isinstance(url, str) and is_allowed_searched_url(url, True)
    ]
    sources = requested_sources or sorted(source_urls)[:5]
    summary = clean_country_history_summary(parsed.get("summary"), config["display_name"])
    history = {
        "country": config["display_name"],
        "title": "Recent history",
        "summary": summary,
        "sources": sources[:5],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": f"openai-web-search:{model or fetch_ai_picks.DEFAULT_OPENAI_MODEL}",
    }
    story_store.write_country_history(country_name, history, stale_after=stale_after(COUNTRY_HISTORY_TTL))
    return history


def refresh_top_stories(limit: int = 25) -> dict[str, Any]:
    args = argparse.Namespace(
        limit=limit,
        per_query=2,
        discovery_per_query=6,
        secondary_per_query=10,
        rss_per_feed=40,
        window_hours=72,
        delay_seconds=0.0,
        skip_openai=False,
        skip_gdelt=True,
        skip_rss=False,
        skip_discovery=False,
        allow_seeded_fallback=False,
        preview_discovery=False,
        preview_limit=25,
    )
    payload = fetch_ai_picks.build_payload(args)
    story_store.write_story_set("top_stories", payload, stale_after=stale_after(TOP_STORIES_TTL))
    return payload


def seed_from_json_caches() -> None:
    history_seed_path = ROOT / "data" / "generated" / "country_histories_seed.json"
    if history_seed_path.exists():
        payload = json.loads(history_seed_path.read_text())
        for item in payload.get("histories", []):
            country = item.get("country")
            history = item.get("payload")
            if not country or not isinstance(history, dict):
                continue
            if not story_store.read_country_history(country):
                story_store.write_country_history(
                    country,
                    history,
                    stale_after=item.get("staleAfter") or stale_after(COUNTRY_HISTORY_TTL),
                    status=item.get("status") or "ready",
                    warning=item.get("warning"),
                )

    top_path = ROOT / "data" / "cache" / "ai_picks.json"
    if top_path.exists() and not story_store.read_story_set("top_stories"):
        payload = json.loads(top_path.read_text())
        story_store.write_story_set("top_stories", payload, stale_after=stale_after(timedelta(minutes=1)))

    country_path = ROOT / "data" / "cache" / "briefings.json"
    if country_path.exists():
        payload = json.loads(country_path.read_text())
        for country, briefing in payload.get("countries", {}).items():
            if not story_store.read_country_briefing(country):
                story_store.write_country_briefing(country, briefing, stale_after=stale_after(timedelta(minutes=1)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the SQLite story store.")
    parser.add_argument("--seed", action="store_true", help="Seed SQLite from existing JSON caches.")
    parser.add_argument("--top-stories", action="store_true", help="Refresh top stories.")
    parser.add_argument("--countries", default="", help="Comma-separated countries to refresh.")
    parser.add_argument("--histories", default="", help="Comma-separated countries whose Recent history should be refreshed.")
    parser.add_argument("--stale-countries", type=int, default=0, help="Refresh this many stale countries.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seed:
        seed_from_json_caches()
    if args.top_stories:
        payload = refresh_top_stories()
        print(f"Refreshed {len(payload.get('picks', []))} top stories")
    countries = [item.strip() for item in args.countries.split(",") if item.strip()]
    if args.stale_countries:
        countries.extend(story_store.stale_country_names(args.stale_countries))
    histories = [item.strip() for item in args.histories.split(",") if item.strip()]
    for country in dict.fromkeys(histories):
        try:
            history = refresh_country_history(country)
            print(f"Refreshed {country} history: {len(history.get('summary', '').split())} words")
        except Exception as error:
            print(f"warning: failed to refresh {country} history: {error}", file=sys.stderr)
    for country in dict.fromkeys(countries):
        try:
            briefing = refresh_country(country)
            print(f"Refreshed {country}: {len(briefing.get('stories', []))} stories")
        except Exception as error:
            print(f"warning: failed to refresh {country}: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
