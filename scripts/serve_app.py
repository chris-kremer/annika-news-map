#!/usr/bin/env python3

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import fetch_briefings


ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "cache" / "briefings.json"
CACHE_TTL = timedelta(hours=24)


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {"generatedAt": None, "countries": {}}
    try:
        return json.loads(CACHE_PATH.read_text())
    except json.JSONDecodeError:
        return {"generatedAt": None, "countries": {}}


def save_cache(payload: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


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


def fetch_country(country_name: str) -> dict:
    env = fetch_briefings.load_env()
    api_token = env.get("THE_NEWS_API_TOKEN")
    if not api_token:
        raise RuntimeError("Missing THE_NEWS_API_TOKEN in .env.local")

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

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/briefing":
            self.handle_briefing_request(parsed)
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

        cache = load_cache()
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
        save_cache(cache)
        self.end_json({"country": country_name, "briefing": briefing, "fromCache": False})


def main() -> int:
    host = "127.0.0.1"
    port = 4173
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Serving Anakin's News Map on http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
