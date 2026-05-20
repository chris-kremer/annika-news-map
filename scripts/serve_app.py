#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fetch_briefings
import fetch_ai_picks
import fetch_important_spots
import refresh_story_store
import story_store


ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "cache" / "briefings.json"
SPOT_CACHE_PATH = ROOT / "data" / "cache" / "important_spots.json"
AI_PICKS_CACHE_PATH = ROOT / "data" / "cache" / "ai_picks.json"
AI_PICKS_MORE_CACHE_PATH = ROOT / "data" / "cache" / "ai_picks_more.json"
AI_PICKS_STATIC_PATH = ROOT / "data" / "generated" / "ai_picks.json"
POLYMARKET_CACHE_PATH = ROOT / "data" / "cache" / "polymarket_prices.json"
CACHE_TTL = timedelta(hours=24)
AI_PICKS_CACHE_TTL = timedelta(hours=6)
POLYMARKET_CACHE_TTL = timedelta(minutes=30)
AI_PICKS_TARGET_COUNT = 25
AI_PICKS_PAGE_LIMIT = 5
DEFAULT_BRIEFING_REFRESH_COUNTRIES = [
    "United States of America",
    "Germany",
    "Brazil",
    "Japan",
    "India",
    "Nigeria",
    "Ukraine",
    "Chad",
]


def env_int(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


AI_PICKS_BACKGROUND_ENABLED = os.environ.get("AI_PICKS_BACKGROUND_REFRESH", "0") == "1"
AI_PICKS_MORE_BACKGROUND_ENABLED = os.environ.get("AI_PICKS_MORE_BACKGROUND_REFRESH", "0") == "1"
BRIEFINGS_BACKGROUND_ENABLED = os.environ.get("BRIEFINGS_BACKGROUND_REFRESH", "1") != "0"
IMPORTANT_SPOTS_BACKGROUND_ENABLED = os.environ.get("IMPORTANT_SPOTS_BACKGROUND_REFRESH", "1") != "0"
BRIEFINGS_REFRESH_INTERVAL = timedelta(
    minutes=env_int("BRIEFINGS_REFRESH_INTERVAL_MINUTES", 60, 5)
)
BRIEFINGS_REFRESH_BATCH_SIZE = env_int("BRIEFINGS_REFRESH_BATCH_SIZE", 5, 1)
ai_picks_refresh_lock = threading.Lock()
ai_picks_refresh_thread: threading.Thread | None = None
ai_picks_more_refresh_lock = threading.Lock()
ai_picks_more_refresh_thread: threading.Thread | None = None
briefings_refresh_lock = threading.Lock()
spots_refresh_lock = threading.Lock()
country_store_refresh_threads: dict[str, threading.Thread] = {}
country_history_refresh_threads: dict[str, threading.Thread] = {}
top_stories_refresh_thread: threading.Thread | None = None


def load_cache(path: Path) -> dict:
    if not path.exists():
        return {"generatedAt": None, "countries": {}}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"generatedAt": None, "countries": {}}


def save_cache(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def parse_cached_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_fresh(country_payload: dict) -> bool:
    cached_at = parse_cached_at(country_payload.get("cachedAt"))
    if not cached_at:
        return False
    return datetime.now(timezone.utc) - cached_at < CACHE_TTL


def env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def is_ai_picks_fresh(payload: dict) -> bool:
    generated_at = parse_cached_at(payload.get("generatedAt"))
    if not generated_at:
        return False
    return datetime.now(timezone.utc) - generated_at < AI_PICKS_CACHE_TTL


def is_polymarket_fresh(entry: dict) -> bool:
    cached_at = parse_cached_at(entry.get("cachedAt"))
    if not cached_at:
        return False
    return datetime.now(timezone.utc) - cached_at < POLYMARKET_CACHE_TTL


def latest_iso_timestamp(*values: str | None) -> str | None:
    parsed_values = [(parse_cached_at(value), value) for value in values if value]
    valid_values = [(parsed, value) for parsed, value in parsed_values if parsed]
    if not valid_values:
        return None
    return max(valid_values, key=lambda item: item[0])[1]


def cache_generated_at(payload: dict) -> datetime | None:
    return parse_cached_at(payload.get("generatedAt"))


def store_stale_after(payload: dict) -> datetime | None:
    metadata = payload.get("_store") if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        return None
    return parse_cached_at(metadata.get("staleAfter"))


def is_store_payload_stale(payload: dict) -> bool:
    stale_after = store_stale_after(payload)
    if not stale_after:
        return True
    return stale_after <= datetime.now(timezone.utc)


def has_picks(payload: dict) -> bool:
    return bool(payload.get("picks"))


def run_top_stories_store_refresh(reason: str) -> None:
    global top_stories_refresh_thread
    try:
        payload = refresh_story_store.refresh_top_stories(AI_PICKS_TARGET_COUNT)
        print(f"Refreshed top stories store with {len(payload.get('picks', []))} picks ({reason})", flush=True, file=sys.stderr)
    except Exception as error:
        print(f"warning: top stories store refresh failed: {error}", flush=True, file=sys.stderr)


def start_top_stories_store_refresh(reason: str) -> bool:
    global top_stories_refresh_thread
    if top_stories_refresh_thread and top_stories_refresh_thread.is_alive():
        return False
    top_stories_refresh_thread = threading.Thread(target=run_top_stories_store_refresh, args=(reason,), daemon=True)
    top_stories_refresh_thread.start()
    return True


def run_country_store_refresh(country_name: str, reason: str) -> None:
    try:
        briefing = refresh_story_store.refresh_country(country_name)
        print(f"Refreshed country store for {country_name} with {len(briefing.get('stories', []))} stories ({reason})", flush=True, file=sys.stderr)
    except Exception as error:
        print(f"warning: country store refresh failed for {country_name}: {error}", flush=True, file=sys.stderr)
    finally:
        country_store_refresh_threads.pop(country_name, None)


def run_country_history_refresh(country_name: str, reason: str) -> None:
    try:
        history = refresh_story_store.refresh_country_history(country_name)
        source_count = len(history.get("sources", []))
        print(f"Refreshed country history for {country_name} with {source_count} sources ({reason})", flush=True, file=sys.stderr)
    except Exception as error:
        print(f"warning: country history refresh failed for {country_name}: {error}", flush=True, file=sys.stderr)
    finally:
        country_history_refresh_threads.pop(country_name, None)


def attach_country_history(country_name: str, briefing: dict | None) -> dict | None:
    if briefing is None:
        return None
    history = story_store.read_country_history(country_name)
    if not history:
        return briefing
    enriched = dict(briefing)
    enriched["recentHistory"] = {
        key: value
        for key, value in history.items()
        if key != "_store"
    }
    enriched["recentHistory"]["stale"] = is_store_payload_stale(history)
    return enriched


def start_country_store_refresh(country_name: str, reason: str) -> bool:
    existing = country_store_refresh_threads.get(country_name)
    if existing and existing.is_alive():
        return False
    thread = threading.Thread(target=run_country_store_refresh, args=(country_name, reason), daemon=True)
    country_store_refresh_threads[country_name] = thread
    thread.start()
    return True


def start_country_history_refresh(country_name: str, reason: str) -> bool:
    existing = country_history_refresh_threads.get(country_name)
    if existing and existing.is_alive():
        return False
    thread = threading.Thread(target=run_country_history_refresh, args=(country_name, reason), daemon=True)
    country_history_refresh_threads[country_name] = thread
    thread.start()
    return True


def ensure_country_history_refresh(country_name: str, reason: str) -> bool:
    history = story_store.read_country_history(country_name)
    if history and not is_store_payload_stale(history):
        return False
    return start_country_history_refresh(country_name, reason)


def sanitize_ai_picks_payload(payload: dict) -> dict:
    if not payload.get("picks"):
        return payload
    cleaned = dict(payload)
    cleaned["picks"] = fetch_ai_picks.filter_excluded_ai_picks(payload.get("picks", []))
    return cleaned


def build_market_card(url: str, fallback_card: dict | None = None) -> dict:
    try:
        return fetch_important_spots.fetch_polymarket_card(url, fallback_card)
    except Exception:
        if fallback_card:
            return dict(fallback_card)
        return {
            "title": "Polymarket market",
            "url": url,
            "yesProbability": "Unavailable",
            "volume": "Unavailable",
            "resolveDate": "Unavailable",
            "updatedLabel": "Today",
            "note": "Open the linked Polymarket market for the live tape.",
        }
    

def ensure_spot_market_card(spot_id: str, briefing: dict) -> dict:
    config = fetch_important_spots.get_spot_config(spot_id)
    market_url = config.get("marketUrl")
    if not market_url:
        return briefing

    enriched = dict(briefing)
    enriched["marketCard"] = build_market_card(market_url, config.get("marketFallback"))
    return enriched


def fetch_country(country_name: str) -> dict:
    env = fetch_briefings.load_env()
    api_token = env.get("THE_NEWS_API_TOKEN")
    if not api_token:
        raise RuntimeError("Missing THE_NEWS_API_TOKEN")

    config = fetch_briefings.get_country_config(country_name)
    thenews_articles = fetch_briefings.fetch_thenews_articles(config, api_token, limit=5)
    if not thenews_articles:
        thenews_articles = fetch_briefings.fetch_thenews_articles(
            config,
            api_token,
            limit=5,
            window_days=14,
        )
    gdelt_articles = []
    if len(thenews_articles) < 2:
        try:
            gdelt_articles = fetch_briefings.fetch_gdelt_articles(config, limit=3, window_days=14)
        except Exception:
            gdelt_articles = []

    briefing = fetch_briefings.build_country_briefing(
        config,
        thenews_articles,
        gdelt_articles,
        limit=5,
    )
    briefing["cachedAt"] = datetime.now(timezone.utc).isoformat()
    briefing["cacheStatus"] = "fresh"
    return briefing


def fetch_spot(spot_id: str) -> dict:
    env = fetch_important_spots.load_env()
    api_token = env.get("THE_NEWS_API_TOKEN")
    if not api_token:
        raise RuntimeError("Missing THE_NEWS_API_TOKEN")

    config = fetch_important_spots.get_spot_config(spot_id)
    thenews_articles = fetch_important_spots.fetch_spot_articles(config, api_token, limit=5)
    gdelt_articles = []
    if len(thenews_articles) < 2:
        try:
            gdelt_articles = fetch_important_spots.fetch_gdelt_articles(config, limit=3)
        except Exception:
            gdelt_articles = []

    briefing = fetch_important_spots.build_spot_briefing(
        config,
        thenews_articles,
        gdelt_articles,
        limit=5,
    )
    market_url = config.get("marketUrl")
    if market_url:
        briefing["marketCard"] = build_market_card(market_url, config.get("marketFallback"))
    briefing["cachedAt"] = datetime.now(timezone.utc).isoformat()
    briefing["cacheStatus"] = "fresh"
    return briefing


def configured_country_refresh_targets(cache: dict) -> list[str]:
    valid_names = set(fetch_briefings.get_country_names())
    configured = env_list("BRIEFINGS_REFRESH_COUNTRIES")
    cached_names = list(cache.get("countries", {}).keys())
    candidates = configured or cached_names or DEFAULT_BRIEFING_REFRESH_COUNTRIES
    return [name for name in dict.fromkeys(candidates) if name in valid_names]


def configured_spot_refresh_targets(cache: dict) -> list[str]:
    valid_ids = set(fetch_important_spots.get_spot_ids())
    configured = env_list("IMPORTANT_SPOTS_REFRESH_IDS")
    cached_ids = list(cache.get("spots", {}).keys())
    candidates = configured or cached_ids or sorted(valid_ids)
    return [spot_id for spot_id in dict.fromkeys(candidates) if spot_id in valid_ids]


def refresh_stale_country_briefings(reason: str, batch_size: int = BRIEFINGS_REFRESH_BATCH_SIZE) -> int:
    with briefings_refresh_lock:
        cache = load_cache(CACHE_PATH)
        countries = cache.setdefault("countries", {})
        refreshed = 0
        for country_name in configured_country_refresh_targets(cache):
            if refreshed >= batch_size:
                break
            cached = countries.get(country_name)
            if cached and is_fresh(cached):
                continue
            try:
                countries[country_name] = fetch_country(country_name)
                cache["generatedAt"] = datetime.now(timezone.utc).isoformat()
                save_cache(CACHE_PATH, cache)
                refreshed += 1
                print(f"Refreshed country briefing for {country_name} ({reason})", flush=True, file=sys.stderr)
            except Exception as error:
                print(f"warning: country briefing refresh failed for {country_name}: {error}", flush=True, file=sys.stderr)
        return refreshed


def refresh_stale_spot_briefings(reason: str, batch_size: int = BRIEFINGS_REFRESH_BATCH_SIZE) -> int:
    with spots_refresh_lock:
        cache = load_cache(SPOT_CACHE_PATH)
        spots = cache.setdefault("spots", {})
        refreshed = 0
        for spot_id in configured_spot_refresh_targets(cache):
            if refreshed >= batch_size:
                break
            cached = spots.get(spot_id)
            if cached and is_fresh(cached):
                continue
            try:
                spots[spot_id] = fetch_spot(spot_id)
                cache["generatedAt"] = datetime.now(timezone.utc).isoformat()
                save_cache(SPOT_CACHE_PATH, cache)
                refreshed += 1
                print(f"Refreshed important-spot briefing for {spot_id} ({reason})", flush=True, file=sys.stderr)
            except Exception as error:
                print(f"warning: important-spot refresh failed for {spot_id}: {error}", flush=True, file=sys.stderr)
        return refreshed


def fetch_ai_picks_payload(limit: int = 10) -> dict:
    args = fetch_ai_picks.parse_args()
    args.limit = limit
    args.per_query = 2
    args.discovery_per_query = 6
    args.secondary_per_query = 10
    args.rss_per_feed = 40
    args.window_hours = 72
    args.delay_seconds = 0.0
    args.skip_gdelt = True
    args.skip_openai = True
    return fetch_ai_picks.build_payload(args)


def best_available_ai_picks_cache() -> dict:
    static = sanitize_ai_picks_payload(load_cache(AI_PICKS_STATIC_PATH))
    runtime = sanitize_ai_picks_payload(load_cache(AI_PICKS_CACHE_PATH))
    runtime_generated_at = cache_generated_at(runtime)
    static_generated_at = cache_generated_at(static)
    if runtime_generated_at and (
        not static_generated_at or runtime_generated_at >= static_generated_at
    ):
        return runtime
    candidates = [payload for payload in (runtime, static) if has_picks(payload)]
    if not candidates:
        return runtime
    return max(
        candidates,
        key=lambda payload: cache_generated_at(payload) or datetime.min.replace(tzinfo=timezone.utc),
    )


def refresh_ai_picks_cache(limit: int = AI_PICKS_TARGET_COUNT) -> dict:
    with ai_picks_refresh_lock:
        previous = best_available_ai_picks_cache()
        payload = fetch_ai_picks_payload(limit)
        if not payload.get("picks") and previous.get("picks"):
            print(
                "warning: AI picks refresh produced no picks; clearing stale previous picks",
                flush=True,
                file=sys.stderr,
            )
        save_cache(AI_PICKS_CACHE_PATH, payload)
        return payload


def build_ai_picks_more_payload(full: bool = False) -> dict:
    args = fetch_ai_picks.parse_args()
    args.preview_limit = 40 if full else 30
    args.limit = AI_PICKS_TARGET_COUNT if full else AI_PICKS_PAGE_LIMIT
    args.discovery_per_query = 4
    args.secondary_per_query = 6
    args.rss_per_feed = 12
    args.window_hours = 240
    args.delay_seconds = 1.0 if full else 0.0
    if not full:
        args.skip_gdelt = True

    preview = fetch_ai_picks.preview_discovery(args)
    candidates = preview.get("candidates", [])
    discovered = []
    llm_curated = False
    if full:
        env = fetch_ai_picks.load_env()
        try:
            discovered = fetch_ai_picks.curate_discovery_with_openai(candidates, AI_PICKS_TARGET_COUNT, env)
            if discovered:
                llm_curated = True
                discovered = fetch_ai_picks.translate_source_titles_with_openai(discovered, env)
        except Exception as error:
            print(f"warning: AI picks more LLM curation failed: {error}", flush=True, file=sys.stderr)
            discovered = []

    if not discovered:
        for candidate in candidates:
            pick = fetch_ai_picks.candidate_to_pick(candidate)
            if pick:
                discovered.append(pick)
    discovered.sort(key=lambda pick: (pick.get("importance", 0), pick.get("confidence", 0)), reverse=True)
    picks = fetch_ai_picks.filter_excluded_ai_picks(dedupe_pick_pool(discovered))
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "openai-discovery-cache" if llm_curated else "discovery-preview-cache",
        "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
        "picks": picks[:AI_PICKS_TARGET_COUNT],
        "candidateCount": preview.get("candidateCount", 0),
        "warning": preview.get("warning"),
    }


def refresh_ai_picks_more_cache(reason: str, full: bool = True) -> dict:
    with ai_picks_more_refresh_lock:
        previous = sanitize_ai_picks_payload(load_cache(AI_PICKS_MORE_CACHE_PATH))
        payload = build_ai_picks_more_payload(full=full)
        if len(payload.get("picks", [])) < len(previous.get("picks", [])):
            save_cache(AI_PICKS_MORE_CACHE_PATH, previous)
            return previous
        save_cache(AI_PICKS_MORE_CACHE_PATH, payload)
        print(f"AI picks more cache now has {len(payload.get('picks', []))} picks ({reason})", flush=True, file=sys.stderr)
        return payload


def run_ai_picks_more_refresh(reason: str, full: bool = True) -> None:
    try:
        refresh_ai_picks_more_cache(reason, full=full)
    except Exception as error:
        print(f"warning: AI picks more refresh failed: {error}", flush=True, file=sys.stderr)


def start_ai_picks_more_refresh(reason: str, full: bool = True, force: bool = False) -> bool:
    global ai_picks_more_refresh_thread
    if not AI_PICKS_MORE_BACKGROUND_ENABLED and not force:
        return False
    if ai_picks_more_refresh_thread and ai_picks_more_refresh_thread.is_alive():
        return False
    cached = sanitize_ai_picks_payload(load_cache(AI_PICKS_MORE_CACHE_PATH))
    if cached.get("picks") and len(cached.get("picks", [])) >= AI_PICKS_TARGET_COUNT and is_ai_picks_fresh(cached):
        return False
    ai_picks_more_refresh_thread = threading.Thread(target=run_ai_picks_more_refresh, args=(reason, full), daemon=True)
    ai_picks_more_refresh_thread.start()
    return True


def run_ai_picks_refresh(reason: str) -> None:
    try:
        print(f"Refreshing AI picks cache ({reason})", flush=True, file=sys.stderr)
        payload = refresh_ai_picks_cache()
        print(f"AI picks cache now has {len(payload.get('picks', []))} picks", flush=True, file=sys.stderr)
    except Exception as error:
        print(f"warning: AI picks background refresh failed: {error}", flush=True, file=sys.stderr)


def start_ai_picks_refresh(reason: str, force: bool = False) -> bool:
    global ai_picks_refresh_thread
    if not AI_PICKS_BACKGROUND_ENABLED and not force:
        return False
    if ai_picks_refresh_thread and ai_picks_refresh_thread.is_alive():
        return False
    cached = best_available_ai_picks_cache()
    if not force and cached.get("picks") and len(cached.get("picks", [])) >= AI_PICKS_TARGET_COUNT and is_ai_picks_fresh(cached):
        return False
    ai_picks_refresh_thread = threading.Thread(target=run_ai_picks_refresh, args=(reason,), daemon=True)
    ai_picks_refresh_thread.start()
    return True


def ai_picks_scheduler() -> None:
    while True:
        cached = best_available_ai_picks_cache()
        if not cached.get("picks") or len(cached.get("picks", [])) < AI_PICKS_TARGET_COUNT or not is_ai_picks_fresh(cached):
            start_ai_picks_refresh("scheduled")
        time.sleep(AI_PICKS_CACHE_TTL.total_seconds())


def ai_picks_more_scheduler() -> None:
    while True:
        cached = sanitize_ai_picks_payload(load_cache(AI_PICKS_MORE_CACHE_PATH))
        if not cached.get("picks") or len(cached.get("picks", [])) < AI_PICKS_TARGET_COUNT or not is_ai_picks_fresh(cached):
            start_ai_picks_more_refresh("scheduled")
        time.sleep(AI_PICKS_CACHE_TTL.total_seconds())


def regular_story_scheduler() -> None:
    while True:
        top_stories = story_store.read_story_set("top_stories")
        if not top_stories or is_store_payload_stale(top_stories):
            start_top_stories_store_refresh("scheduled")
        if BRIEFINGS_BACKGROUND_ENABLED:
            for country_name in story_store.stale_country_names(BRIEFINGS_REFRESH_BATCH_SIZE):
                start_country_store_refresh(country_name, "scheduled")
        if IMPORTANT_SPOTS_BACKGROUND_ENABLED:
            refresh_stale_spot_briefings("scheduled")
        time.sleep(BRIEFINGS_REFRESH_INTERVAL.total_seconds())


def canonical_story_key(pick: dict) -> str:
    if pick.get("storyKey"):
        return str(pick["storyKey"]).strip().lower()
    theme_text = " ".join(
        [
            str(pick.get("title", "")),
            str(pick.get("summary", "")),
            str(pick.get("whyItMatters", "")),
            str(pick.get("place", "")),
            str(pick.get("country", "")),
        ]
    ).lower()
    if (
        "afghanistan" in theme_text
        and "pakistan" in theme_text
        and any(term in theme_text for term in ["border", "cross-border", "security threat", "attacks"])
    ):
        return "theme:afghanistan-pakistan-border"
    if "hantavirus" in theme_text and "canary" in theme_text:
        return "theme:canary-islands-hantavirus"
    if "sudan" in theme_text and "chad" in theme_text and any(term in theme_text for term in ["border", "refugee", "displacement"]):
        return "theme:chad-sudan-border"
    source_url = ""
    sources = pick.get("sources")
    if isinstance(sources, list) and sources:
        source_url = str(sources[0].get("url", "")).strip().lower()
    if source_url:
        return source_url
    return fetch_ai_picks.story_fingerprint(str(pick.get("title", "")))


def canonical_country_key(pick: dict) -> str:
    return str(pick.get("country") or pick.get("place") or "").split("/")[0].strip().lower()


def dedupe_pick_pool(picks: list[dict], skip_ids: set[str] | None = None, skip_story_keys: set[str] | None = None, skip_countries: set[str] | None = None) -> list[dict]:
    skip_ids = skip_ids or set()
    skip_story_keys = skip_story_keys or set()
    skip_countries = skip_countries or set()
    seen_ids = set(skip_ids)
    seen_story_keys = set(skip_story_keys)
    seen_countries = set(skip_countries)
    deduped = []
    for pick in picks:
        pick_id = str(pick.get("id", "")).strip()
        story_key = canonical_story_key(pick)
        country_key = canonical_country_key(pick)
        if pick_id and pick_id in seen_ids:
            continue
        if story_key and story_key in seen_story_keys:
            continue
        if country_key and country_key in seen_countries:
            continue
        if pick_id:
            seen_ids.add(pick_id)
        if story_key:
            seen_story_keys.add(story_key)
        if country_key:
            seen_countries.add(country_key)
        deduped.append(pick)
    return deduped


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        import sys
        print(f"[{self.address_string()}] {format % args}", flush=True, file=sys.stderr)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self.end_json({"status": "ok"})
            return
        if parsed.path == "/api/briefing":
            self.handle_briefing_request(parsed)
            return
        if parsed.path == "/api/important-spot":
            self.handle_spot_request(parsed)
            return
        if parsed.path == "/api/ai-picks":
            self.handle_ai_picks_request(parsed)
            return
        if parsed.path == "/api/ai-picks/more":
            self.handle_ai_picks_more_request(parsed)
            return
        if parsed.path == "/api/ai-picks/preview":
            self.handle_ai_picks_preview_request(parsed)
            return
        if parsed.path == "/api/polymarket-price":
            self.handle_polymarket_price_request(parsed)
            return
        super().do_GET()

    def handle_polymarket_price_request(self, parsed) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        url = params.get("url", [""])[0].strip()
        if not url or "polymarket.com" not in url:
            self.end_json({"error": "Missing or invalid url"}, status=400)
            return

        cache = load_cache(POLYMARKET_CACHE_PATH)
        prices = cache.setdefault("prices", {})
        cached = prices.get(url)
        if cached and is_polymarket_fresh(cached):
            self.end_json({**cached, "fromCache": True})
            return

        try:
            card = fetch_important_spots.fetch_polymarket_card(url)
            entry = {
                "yesProbability": card.get("yesProbability", "Unavailable"),
                "volume": card.get("volume", "Unavailable"),
                "title": card.get("title", ""),
                "resolveDate": card.get("resolveDate", ""),
                "cachedAt": datetime.now(timezone.utc).isoformat(),
            }
            prices[url] = entry
            cache["generatedAt"] = datetime.now(timezone.utc).isoformat()
            save_cache(POLYMARKET_CACHE_PATH, cache)
            self.end_json({**entry, "fromCache": False})
        except Exception as error:
            if cached:
                self.end_json({**cached, "fromCache": True, "warning": str(error)})
                return
            self.end_json({"error": str(error)}, status=502)

    def handle_briefing_request(self, parsed) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        country_name = params.get("country", [""])[0].strip()
        if not country_name:
            self.end_json({"error": "Missing country"}, status=400)
            return

        valid_names = set(fetch_briefings.get_country_names())
        if country_name not in valid_names:
            self.end_json({"error": f"Unknown country: {country_name}"}, status=404)
            return

        force_refresh = params.get("refresh", ["0"])[0] == "1"
        briefing = story_store.read_country_briefing(country_name)
        history_refreshing = ensure_country_history_refresh(country_name, "api-request")
        if not briefing:
            refreshing = start_country_store_refresh(country_name, "missing-api-request")
            history = story_store.read_country_history(country_name)
            self.end_json(
                {
                    "country": country_name,
                    "briefing": attach_country_history(country_name, {"name": country_name, "stories": []}) if history else None,
                    "fromStore": False,
                    "refreshing": refreshing,
                    "historyRefreshing": history_refreshing or bool(country_history_refresh_threads.get(country_name)),
                    "error": "Briefing is not in the story store yet.",
                },
                status=202,
            )
            return

        stale = is_store_payload_stale(briefing)
        refreshing = False
        if force_refresh or stale:
            refreshing = start_country_store_refresh(country_name, "stale-api-request" if stale else "forced-api-request")
        briefing["cacheStatus"] = "stale" if stale else briefing.get("cacheStatus", "fresh")
        briefing = attach_country_history(country_name, briefing)
        self.end_json(
            {
                "country": country_name,
                "briefing": briefing,
                "fromCache": True,
                "fromStore": True,
                "stale": stale,
                "refreshing": refreshing or bool(country_store_refresh_threads.get(country_name)),
                "historyRefreshing": history_refreshing or bool(country_history_refresh_threads.get(country_name)),
            }
        )

    def handle_spot_request(self, parsed) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        spot_id = params.get("spot", [""])[0].strip()
        if not spot_id:
            self.end_json({"error": "Missing spot"}, status=400)
            return

        valid_ids = set(fetch_important_spots.get_spot_ids())
        if spot_id not in valid_ids:
            self.end_json({"error": f"Unknown spot: {spot_id}"}, status=404)
            return

        cache = load_cache(SPOT_CACHE_PATH)
        spots = cache.setdefault("spots", {})
        cached = spots.get(spot_id)
        force_refresh = params.get("refresh", ["0"])[0] == "1"

        if cached and is_fresh(cached) and not force_refresh:
            briefing = ensure_spot_market_card(spot_id, cached)
            if briefing is not cached:
                spots[spot_id] = briefing
                cache["generatedAt"] = datetime.now(timezone.utc).isoformat()
                save_cache(SPOT_CACHE_PATH, cache)
            self.end_json({"spot": spot_id, "briefing": briefing, "fromCache": True})
            return

        try:
            briefing = fetch_spot(spot_id)
        except Exception as error:
            if cached:
                fallback = dict(cached)
                fallback["cacheStatus"] = "stale"
                self.end_json(
                    {
                        "spot": spot_id,
                        "briefing": fallback,
                        "fromCache": True,
                        "warning": str(error),
                    }
                )
                return
            self.end_json({"error": str(error)}, status=502)
            return

        spots[spot_id] = briefing
        cache["generatedAt"] = datetime.now(timezone.utc).isoformat()
        save_cache(SPOT_CACHE_PATH, cache)
        self.end_json({"spot": spot_id, "briefing": briefing, "fromCache": False})

    def handle_ai_picks_request(self, parsed) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        force_refresh = params.get("refresh", ["0"])[0] == "1"
        try:
            offset = max(0, int(params.get("offset", ["0"])[0]))
            limit = max(1, min(20, int(params.get("limit", ["5"])[0])))
        except ValueError:
            self.end_json({"error": "Invalid offset or limit"}, status=400)
            return
        stored = story_store.read_story_set("top_stories")
        if stored:
            stale = is_store_payload_stale(stored)
            refreshing = False
            if force_refresh or stale:
                refreshing = start_top_stories_store_refresh("stale-api-request" if stale else "forced-api-request")
            picks = stored.get("picks", [])
            sliced = dict(stored)
            sliced.pop("_store", None)
            sliced["picks"] = picks[offset : offset + limit]
            metadata = stored.get("_store", {})
            self.end_json(
                {
                    **sliced,
                    "fromCache": True,
                    "fromStore": True,
                    "stale": stale,
                    "refreshing": refreshing or bool(top_stories_refresh_thread and top_stories_refresh_thread.is_alive()),
                    "offset": offset,
                    "limit": limit,
                    "totalAvailable": len(picks),
                    "moreCacheGeneratedAt": None,
                    "latestCacheGeneratedAt": latest_iso_timestamp(stored.get("generatedAt"), metadata.get("refreshedAt")),
                    "store": metadata,
                    "warning": metadata.get("warning"),
                }
            )
            return

        refreshing = start_top_stories_store_refresh("missing-api-request")

        self.end_json(
            {
                "generatedAt": None,
                "provider": "warming-store",
                "windowHours": 72,
                "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
                "picks": [],
                "fromCache": True,
                "fromStore": False,
                "refreshing": refreshing or bool(top_stories_refresh_thread and top_stories_refresh_thread.is_alive()),
                "offset": offset,
                "limit": limit,
                "totalAvailable": 0,
                "moreCacheGeneratedAt": None,
                "latestCacheGeneratedAt": None,
            },
            status=202,
        )

    def handle_ai_picks_preview_request(self, parsed) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        try:
            limit = max(1, min(50, int(params.get("limit", ["25"])[0])))
        except ValueError:
            self.end_json({"error": "Invalid limit"}, status=400)
            return
        args = fetch_ai_picks.parse_args()
        args.limit = limit
        args.preview_limit = limit
        args.discovery_per_query = 4
        args.secondary_per_query = 6
        args.rss_per_feed = 8
        args.window_hours = 240
        args.delay_seconds = 3.0
        try:
            payload = fetch_ai_picks.preview_discovery(args)
        except Exception as error:
            self.end_json({"error": str(error)}, status=502)
            return
        self.end_json(payload)

    def handle_ai_picks_more_request(self, parsed) -> None:
        params = urllib.parse.parse_qs(parsed.query)
        try:
            limit = max(1, min(10, int(params.get("limit", ["5"])[0])))
        except ValueError:
            self.end_json({"error": "Invalid limit"}, status=400)
            return
        skip_ids = {item for item in params.get("skipId", []) if item}
        skip_story_keys = {item for item in params.get("skipStory", []) if item}
        skip_countries = {item for item in params.get("skipCountry", []) if item}

        stored = story_store.read_story_set("top_stories")
        if not stored:
            refreshing = start_top_stories_store_refresh("missing-more-request")
            self.end_json(
                {
                    "generatedAt": None,
                    "provider": "warming-store",
                    "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
                    "picks": [],
                    "limit": limit,
                    "totalAvailable": 0,
                    "refreshing": refreshing,
                    "warning": "Top stories are not in the story store yet.",
                },
                status=202,
            )
            return

        stale = is_store_payload_stale(stored)
        refreshing = False
        if stale:
            refreshing = start_top_stories_store_refresh("stale-more-request")
        pool = dedupe_pick_pool(
            stored.get("picks", []),
            skip_ids=skip_ids,
            skip_story_keys=skip_story_keys,
            skip_countries=skip_countries,
        )
        metadata = stored.get("_store", {})
        self.end_json(
            {
                "generatedAt": stored.get("generatedAt"),
                "provider": stored.get("provider", "story-store"),
                "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
                "picks": pool[:limit],
                "limit": limit,
                "totalAvailable": len(pool),
                "candidateCount": len(stored.get("picks", [])),
                "fromStore": True,
                "stale": stale,
                "refreshing": refreshing or bool(top_stories_refresh_thread and top_stories_refresh_thread.is_alive()),
                "warning": metadata.get("warning"),
            }
        )


def main() -> int:
    import sys
    import traceback
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 4173))
    print(f"Starting server on {host}:{port}", flush=True)
    try:
        server = ThreadingHTTPServer((host, port), AppHandler)
    except Exception:
        print("FAILED to bind socket:", flush=True)
        traceback.print_exc()
        return 1
    print(f"Serving Pumpkin News on http://{host}:{port}/", flush=True)
    refresh_story_store.seed_from_json_caches()
    if not story_store.read_story_set("top_stories") or is_store_payload_stale(story_store.read_story_set("top_stories") or {}):
        start_top_stories_store_refresh("startup")
    if AI_PICKS_BACKGROUND_ENABLED:
        start_ai_picks_refresh("startup")
        threading.Thread(target=ai_picks_scheduler, daemon=True).start()
    if AI_PICKS_MORE_BACKGROUND_ENABLED:
        start_ai_picks_more_refresh("startup")
        threading.Thread(target=ai_picks_more_scheduler, daemon=True).start()
    if BRIEFINGS_BACKGROUND_ENABLED or IMPORTANT_SPOTS_BACKGROUND_ENABLED:
        threading.Thread(target=regular_story_scheduler, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
    except Exception:
        print("serve_forever crashed:", flush=True)
        traceback.print_exc(file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
