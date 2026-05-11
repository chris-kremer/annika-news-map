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
AI_PICKS_BACKGROUND_ENABLED = os.environ.get("AI_PICKS_BACKGROUND_REFRESH", "0") == "1"
AI_PICKS_MORE_BACKGROUND_ENABLED = os.environ.get("AI_PICKS_MORE_BACKGROUND_REFRESH", "1") == "1"
ai_picks_refresh_lock = threading.Lock()
ai_picks_refresh_thread: threading.Thread | None = None
ai_picks_more_refresh_lock = threading.Lock()
ai_picks_more_refresh_thread: threading.Thread | None = None


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


def has_picks(payload: dict) -> bool:
    return bool(payload.get("picks"))


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


def fetch_ai_picks_payload(limit: int = 10) -> dict:
    args = fetch_ai_picks.parse_args()
    args.limit = limit
    args.per_query = 2
    args.discovery_per_query = 6
    args.secondary_per_query = 10
    args.rss_per_feed = 12
    args.window_hours = 240
    args.delay_seconds = 3.0
    return fetch_ai_picks.build_payload(args)


def best_available_ai_picks_cache() -> dict:
    static = load_cache(AI_PICKS_STATIC_PATH)
    runtime = load_cache(AI_PICKS_CACHE_PATH)
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
        if len(payload.get("picks", [])) < len(previous.get("picks", [])):
            print(
                f"warning: keeping existing AI picks cache with {len(previous.get('picks', []))} picks; refresh only produced {len(payload.get('picks', []))}",
                flush=True,
                file=sys.stderr,
            )
            save_cache(AI_PICKS_CACHE_PATH, previous)
            return previous
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
    picks = dedupe_pick_pool(discovered)
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
        previous = load_cache(AI_PICKS_MORE_CACHE_PATH)
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


def start_ai_picks_more_refresh(reason: str, full: bool = True) -> bool:
    global ai_picks_more_refresh_thread
    if ai_picks_more_refresh_thread and ai_picks_more_refresh_thread.is_alive():
        return False
    cached = load_cache(AI_PICKS_MORE_CACHE_PATH)
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
        cached = load_cache(AI_PICKS_MORE_CACHE_PATH)
        if not cached.get("picks") or len(cached.get("picks", [])) < AI_PICKS_TARGET_COUNT or not is_ai_picks_fresh(cached):
            start_ai_picks_more_refresh("scheduled")
        time.sleep(AI_PICKS_CACHE_TTL.total_seconds())


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

        cache = load_cache(CACHE_PATH)
        countries = cache.setdefault("countries", {})
        cached = countries.get(country_name)
        force_refresh = params.get("refresh", ["0"])[0] == "1"

        if cached and is_fresh(cached) and not force_refresh:
            payload = {"country": country_name, "briefing": cached, "fromCache": True}
            self.end_json(payload)
            return

        try:
            briefing = fetch_country(country_name)
        except Exception as error:
            if cached:
                fallback = dict(cached)
                fallback["cacheStatus"] = "stale"
                payload = {
                    "country": country_name,
                    "briefing": fallback,
                    "fromCache": True,
                    "warning": str(error),
                }
                self.end_json(payload)
                return

            self.end_json({"error": str(error)}, status=502)
            return

        countries[country_name] = briefing
        cache["generatedAt"] = datetime.now(timezone.utc).isoformat()
        save_cache(CACHE_PATH, cache)
        self.end_json({"country": country_name, "briefing": briefing, "fromCache": False})

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
        cached = best_available_ai_picks_cache()
        more_cache = load_cache(AI_PICKS_MORE_CACHE_PATH)
        refreshing = False
        warning = None

        needs_refresh = (
            force_refresh
            or not cached.get("picks")
            or not is_ai_picks_fresh(cached)
            or len(cached.get("picks", [])) < AI_PICKS_TARGET_COUNT
        )
        if needs_refresh:
            try:
                cached = refresh_ai_picks_cache()
            except Exception as error:
                warning = str(error)
                refreshing = start_ai_picks_refresh("api-request", force=force_refresh)

        if cached.get("picks"):
            sliced = dict(cached)
            sliced["picks"] = cached.get("picks", [])[offset : offset + limit]
            self.end_json(
                {
                    **sliced,
                    "fromCache": True,
                    "refreshing": refreshing or bool(ai_picks_refresh_thread and ai_picks_refresh_thread.is_alive()),
                    "offset": offset,
                    "limit": limit,
                    "totalAvailable": len(cached.get("picks", [])),
                    "moreCacheGeneratedAt": more_cache.get("generatedAt"),
                    "latestCacheGeneratedAt": latest_iso_timestamp(cached.get("generatedAt"), more_cache.get("generatedAt")),
                    "warning": warning,
                }
            )
            return

        self.end_json(
            {
                "generatedAt": None,
                "provider": "warming-cache",
                "windowHours": 240,
                "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
                "picks": [],
                "fromCache": True,
                "refreshing": True,
                "offset": offset,
                "limit": limit,
                "totalAvailable": 0,
                "moreCacheGeneratedAt": more_cache.get("generatedAt"),
                "latestCacheGeneratedAt": latest_iso_timestamp(more_cache.get("generatedAt")),
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

        base_cache = best_available_ai_picks_cache()
        more_cache = load_cache(AI_PICKS_MORE_CACHE_PATH)
        base_picks = dedupe_pick_pool(
            base_cache.get("picks", []),
            skip_ids=skip_ids,
            skip_story_keys=skip_story_keys,
            skip_countries=skip_countries,
        )
        cached_more_picks = dedupe_pick_pool(
            more_cache.get("picks", []),
            skip_ids=skip_ids,
            skip_story_keys=skip_story_keys,
            skip_countries=skip_countries,
        )
        cached_pool = dedupe_pick_pool(
            base_picks + cached_more_picks,
            skip_ids=skip_ids,
            skip_story_keys=skip_story_keys,
            skip_countries=skip_countries,
        )

        if len(cached_pool) >= limit:
            refreshing = start_ai_picks_more_refresh("more-request")
            self.end_json(
                {
                    "generatedAt": more_cache.get("generatedAt") or base_cache.get("generatedAt") or datetime.now(timezone.utc).isoformat(),
                    "provider": "cache+background-discovery",
                    "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
                    "picks": cached_pool[:limit],
                    "limit": limit,
                    "totalAvailable": len(cached_pool),
                    "candidateCount": more_cache.get("candidateCount", 0),
                    "refreshing": refreshing or bool(ai_picks_more_refresh_thread and ai_picks_more_refresh_thread.is_alive()),
                    "warning": more_cache.get("warning"),
                }
            )
            return

        warning = None
        candidate_count = more_cache.get("candidateCount", 0)
        fast_picks = []
        try:
            fast_payload = build_ai_picks_more_payload(full=False)
            save_cache(AI_PICKS_MORE_CACHE_PATH, fast_payload)
            candidate_count = fast_payload.get("candidateCount", candidate_count)
            fast_picks = fast_payload.get("picks", [])
            warning = fast_payload.get("warning")
        except Exception as error:
            warning = str(error)

        refreshing = start_ai_picks_more_refresh("more-request")
        pool = dedupe_pick_pool(
            cached_pool + fast_picks,
            skip_ids=skip_ids,
            skip_story_keys=skip_story_keys,
            skip_countries=skip_countries,
        )
        self.end_json(
            {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "provider": "cache+discovery-preview",
                "selectionPrinciple": fetch_ai_picks.SELECTION_PRINCIPLE,
                "picks": pool[:limit],
                "limit": limit,
                "totalAvailable": len(pool),
                "candidateCount": candidate_count,
                "refreshing": refreshing or bool(ai_picks_more_refresh_thread and ai_picks_more_refresh_thread.is_alive()),
                "warning": warning,
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
    if AI_PICKS_BACKGROUND_ENABLED:
        start_ai_picks_refresh("startup")
        threading.Thread(target=ai_picks_scheduler, daemon=True).start()
    if AI_PICKS_MORE_BACKGROUND_ENABLED:
        start_ai_picks_more_refresh("startup")
        threading.Thread(target=ai_picks_more_scheduler, daemon=True).start()
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
