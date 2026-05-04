#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fetch_briefings
import fetch_important_spots


ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "cache" / "briefings.json"
SPOT_CACHE_PATH = ROOT / "data" / "cache" / "important_spots.json"
CACHE_TTL = timedelta(hours=24)


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


def build_market_card(url: str, fallback_card: dict | None = None) -> dict:
    if fallback_card:
        return dict(fallback_card)
    try:
        return fetch_important_spots.fetch_polymarket_card(url)
    except Exception:
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
    if not market_url or briefing.get("marketCard"):
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
    gdelt_articles = []
    if len(thenews_articles) < 2:
        try:
            gdelt_articles = fetch_briefings.fetch_gdelt_articles(config, limit=3)
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
        super().do_GET()

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
    print(f"Serving Anakin's News Map on http://{host}:{port}/", flush=True)
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
