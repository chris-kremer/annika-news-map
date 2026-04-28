#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import subprocess
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_important_spots


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
OUTPUT_PATH = ROOT / "data" / "generated" / "conflict_events.json"
ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_API_URL = "https://acleddata.com/api/acled/read"
UCDP_API_URL = "https://ucdpapi.pcr.uu.se/api/gedevents/26.01.26.03"
WINDOW_DAYS = 30

MANUAL_HOTSPOTS = [
    {
        "id": "ukr-donetsk",
        "label": "Eastern Ukraine frontline",
        "conflict": "Russo-Ukrainian war",
        "kind": "frontline",
        "lat": 48.25,
        "lon": 37.8,
        "weight": 10,
        "countries": ["Ukraine", "Russia", "Belarus"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Russo-Ukrainian_war",
        "marketUrl": "https://polymarket.com/event/russia-x-ukraine-ceasefire-before-2027",
        "marketFallback": {
            "title": "Russia x Ukraine ceasefire by end of 2026?",
            "url": "https://polymarket.com/event/russia-x-ukraine-ceasefire-before-2027",
            "yesProbability": "26%",
            "volume": "$14,502,614",
            "resolveDate": "2026-12-31",
            "updatedLabel": "Apr 28, 2026",
            "note": "Prediction-market pricing from Polymarket. This is a market signal, not a forecast guarantee.",
        },
    },
    {
        "id": "ukr-zaporizhzhia",
        "label": "Southern Ukraine fighting",
        "conflict": "Russo-Ukrainian war",
        "kind": "frontline",
        "lat": 47.1,
        "lon": 35.2,
        "weight": 8,
        "countries": ["Ukraine", "Russia", "Belarus"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Russo-Ukrainian_war",
        "marketUrl": "https://polymarket.com/event/russia-x-ukraine-ceasefire-before-2027",
        "marketFallback": {
            "title": "Russia x Ukraine ceasefire by end of 2026?",
            "url": "https://polymarket.com/event/russia-x-ukraine-ceasefire-before-2027",
            "yesProbability": "26%",
            "volume": "$14,502,614",
            "resolveDate": "2026-12-31",
            "updatedLabel": "Apr 28, 2026",
            "note": "Prediction-market pricing from Polymarket. This is a market signal, not a forecast guarantee.",
        },
    },
    {
        "id": "gaza-strip",
        "label": "Gaza fighting",
        "conflict": "Iran–Israel conflicts",
        "kind": "urban-war",
        "lat": 31.42,
        "lon": 34.36,
        "weight": 9,
        "countries": ["Israel", "Palestine", "Iran"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Iran%E2%80%93Israel_proxy_conflict",
    },
    {
        "id": "south-lebanon",
        "label": "South Lebanon strikes",
        "conflict": "Iran–Israel conflicts",
        "kind": "cross-border",
        "lat": 33.27,
        "lon": 35.38,
        "weight": 6,
        "countries": ["Israel", "Lebanon", "Iran"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Iran%E2%80%93Israel_proxy_conflict",
        "marketUrl": "https://polymarket.com/event/will-hamaz-disarm-by-december-31",
        "marketFallback": {
            "title": "Will Hamas agree to disarm by...?",
            "url": "https://polymarket.com/event/will-hamaz-disarm-by-december-31",
            "yesProbability": "17%",
            "volume": "$1,661,246",
            "resolveDate": "2026-06-30",
            "updatedLabel": "Apr 28, 2026",
            "note": 'Prediction-market pricing from Polymarket. Current leading branch is "June 30, 2026." This is a market signal, not a forecast guarantee.',
        },
    },
    {
        "id": "red-sea-yemen",
        "label": "Red Sea / Yemen attacks",
        "conflict": "Yemeni civil war",
        "kind": "missile-strike",
        "lat": 15.3,
        "lon": 42.7,
        "weight": 7,
        "countries": ["Yemen", "Saudi Arabia", "United Arab Emirates", "Israel"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Yemeni_civil_war_(2014%E2%80%93present)",
    },
    {
        "id": "khartoum",
        "label": "Khartoum fighting",
        "conflict": "Sudanese civil wars",
        "kind": "urban-war",
        "lat": 15.57,
        "lon": 32.53,
        "weight": 9,
        "countries": ["Sudan", "Chad", "Egypt", "Ethiopia", "Libya"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Sudanese_Civil_War",
        "marketUrl": "https://polymarket.com/event/sudan-civil-war-ceasefire-by",
        "marketFallback": {
            "title": "Sudan civil war ceasefire by...?",
            "url": "https://polymarket.com/event/sudan-civil-war-ceasefire-by",
            "yesProbability": "5%",
            "volume": "$61,515",
            "resolveDate": "2026-06-30",
            "updatedLabel": "Apr 28, 2026",
            "note": 'Prediction-market pricing from Polymarket. Current leading branch is "June 30, 2026." This is a market signal, not a forecast guarantee.',
        },
    },
    {
        "id": "darfur",
        "label": "Darfur fighting",
        "conflict": "Sudanese civil wars",
        "kind": "frontline",
        "lat": 13.62,
        "lon": 24.25,
        "weight": 8,
        "countries": ["Sudan", "Chad", "Libya"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Sudanese_Civil_War",
        "marketUrl": "https://polymarket.com/event/sudan-civil-war-ceasefire-by",
        "marketFallback": {
            "title": "Sudan civil war ceasefire by...?",
            "url": "https://polymarket.com/event/sudan-civil-war-ceasefire-by",
            "yesProbability": "5%",
            "volume": "$61,515",
            "resolveDate": "2026-06-30",
            "updatedLabel": "Apr 28, 2026",
            "note": 'Prediction-market pricing from Polymarket. Current leading branch is "June 30, 2026." This is a market signal, not a forecast guarantee.',
        },
    },
    {
        "id": "sahel-tri-border",
        "label": "Sahel insurgency belt",
        "conflict": "Islamist insurgencies in the Maghreb",
        "kind": "insurgency",
        "lat": 14.9,
        "lon": -0.2,
        "weight": 8,
        "countries": ["Mali", "Burkina Faso", "Niger", "Benin", "Togo"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Insurgency_in_the_Maghreb_(2002%E2%80%93present)",
    },
    {
        "id": "lake-chad",
        "label": "Lake Chad / Boko Haram activity",
        "conflict": "Civil conflicts in Nigeria",
        "kind": "insurgency",
        "lat": 13.0,
        "lon": 13.4,
        "weight": 7,
        "countries": ["Nigeria", "Niger", "Cameroon", "Chad"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Communal_conflicts_in_Nigeria",
    },
    {
        "id": "cameroon-far-north",
        "label": "Far North Cameroon violence",
        "conflict": "Cameroonian conflicts",
        "kind": "insurgency",
        "lat": 10.65,
        "lon": 14.33,
        "weight": 5,
        "countries": ["Cameroon", "Nigeria", "Niger", "Chad"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Cameroonian_Civil_War_(disambiguation)",
    },
    {
        "id": "myanmar-sagaing",
        "label": "Sagaing / Myanmar fighting",
        "conflict": "Myanmar civil war",
        "kind": "frontline",
        "lat": 23.75,
        "lon": 95.7,
        "weight": 8,
        "countries": ["Myanmar", "India", "Bangladesh", "Thailand", "China"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Myanmar_civil_war",
    },
    {
        "id": "drc-kivu",
        "label": "Eastern DRC / Kivu clashes",
        "conflict": "Kivu conflict",
        "kind": "insurgency",
        "lat": -1.68,
        "lon": 29.23,
        "weight": 7,
        "countries": ["Congo (Democratic Republic of the)", "Rwanda", "Uganda", "Burundi"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Kivu_conflict",
    },
    {
        "id": "kashmir-line",
        "label": "Kashmir militarized zone",
        "conflict": "Kashmir conflict",
        "kind": "border-conflict",
        "lat": 34.23,
        "lon": 74.85,
        "weight": 6,
        "countries": ["India", "Pakistan", "China"],
        "sourceUrl": "https://en.wikipedia.org/wiki/Kashmir_conflict",
        "marketUrl": "https://polymarket.com/event/india-strike-on-pakistan-by",
        "marketFallback": {
            "title": "India strike on Pakistan by...?",
            "url": "https://polymarket.com/event/india-strike-on-pakistan-by",
            "yesProbability": "27%",
            "volume": "$938,647",
            "resolveDate": "2026-12-31",
            "updatedLabel": "Apr 15, 2026",
            "note": 'Prediction-market pricing from Polymarket. Current leading branch is "December 31, 2026." This is a market signal, not a forecast guarantee.',
        },
    },
]


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


def curl_json_with_headers(
    url: str,
    headers: list[str],
    method: str = "GET",
    data: list[str] | None = None,
    insecure: bool = False,
) -> object:
    cmd = ["curl", "-sfL", "-X", method]
    if insecure:
        cmd.append("--insecure")
    for header in headers:
        cmd.extend(["-H", header])
    if data:
        cmd.extend(data)
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"curl failed for {url}")
    return json.loads(result.stdout)


def get_acled_token(env: dict[str, str]) -> str | None:
    username = env.get("ACLED_USERNAME")
    password = env.get("ACLED_PASSWORD")
    if not username or not password:
        return None

    payload = curl_json_with_headers(
        ACLED_TOKEN_URL,
        headers=["Content-Type: application/x-www-form-urlencoded"],
        method="POST",
        data=[
            "--data-urlencode",
            f"username={username}",
            "--data-urlencode",
            f"password={password}",
            "--data-urlencode",
            "grant_type=password",
            "--data-urlencode",
            "client_id=acled",
            "--data-urlencode",
            "scope=authenticated",
        ],
        insecure=True,
    )
    return payload.get("access_token")


def fetch_acled_events(access_token: str) -> list[dict]:
    start_date = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    params = {
        "_format": "json",
        "disorder_type": "Political violence",
        "event_date": start_date,
        "event_date_where": ">=",
        "event_type": "Battles|Explosions/Remote violence|Violence against civilians",
        "event_type_where": "=",
        "fields": "event_id_cnty|event_date|country|location|latitude|longitude|event_type|sub_event_type|fatalities|notes|geo_precision",
        "limit": "5000",
    }
    url = f"{ACLED_API_URL}?{urllib.parse.urlencode(params)}"
    payload = curl_json_with_headers(
        url,
        headers=[
            f"Authorization: Bearer {access_token}",
            "Content-Type: application/json",
        ],
        insecure=True,
    )
    if payload.get("status") != 200:
        raise RuntimeError(payload.get("message") or "ACLED request failed")
    return payload.get("data") or []


def fetch_ucdp_events(access_token: str) -> list[dict]:
    start_date = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events: list[dict] = []
    page = 1

    while True:
        params = {
            "pagesize": "1000",
            "page": str(page),
            "StartDate": start_date,
            "EndDate": end_date,
        }
        url = f"{UCDP_API_URL}?{urllib.parse.urlencode(params)}"
        payload = curl_json_with_headers(
            url,
            headers=[f"x-ucdp-access-token: {access_token}"],
            insecure=True,
        )
        rows = payload.get("Result") or []
        events.extend(rows)
        next_page = payload.get("NextPageUrl")
        if not next_page:
            break
        page += 1
        if page > 10:
            break

    return events


def build_hotspots_from_acled(events: list[dict]) -> list[dict]:
    buckets: dict[tuple[float, float, str], dict] = {}
    grouped_events: dict[tuple[float, float, str], list[dict]] = defaultdict(list)

    for event in events:
        try:
            lat = float(event["latitude"])
            lon = float(event["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if int(event.get("geo_precision") or 9) > 2:
            continue

        rounded_lat = round(lat * 2) / 2
        rounded_lon = round(lon * 2) / 2
        kind = event.get("event_type") or "Political violence"
        key = (rounded_lat, rounded_lon, kind)
        grouped_events[key].append(event)

    for key, bucket_events in grouped_events.items():
        lat, lon, kind = key
        countries = sorted({event.get("country") for event in bucket_events if event.get("country")})
        bucket = {
            "id": f"acled-{len(buckets)+1}",
            "label": bucket_events[0].get("location") or bucket_events[0].get("country") or "Conflict hotspot",
            "conflict": kind,
            "kind": kind.lower().replace("/", "-").replace(" ", "-"),
            "lat": lat,
            "lon": lon,
            "weight": min(10, 3 + len(bucket_events)),
            "countries": countries,
            "sourceUrl": "",
            "eventCount": len(bucket_events),
            "fatalities": sum(int(float(event.get("fatalities") or 0)) for event in bucket_events),
        }
        buckets[key] = bucket

    hotspots = list(buckets.values())
    hotspots.sort(key=lambda item: (item.get("weight", 0), item.get("fatalities", 0)), reverse=True)
    return hotspots[:120]


def build_hotspots_from_ucdp(events: list[dict]) -> list[dict]:
    buckets: dict[tuple[float, float, str], list[dict]] = defaultdict(list)

    for event in events:
        try:
            lat = float(event["latitude"])
            lon = float(event["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if int(event.get("where_prec") or 9) > 2:
            continue

        rounded_lat = round(lat * 2) / 2
        rounded_lon = round(lon * 2) / 2
        kind = event.get("type_of_violence", "Violence")
        key = (rounded_lat, rounded_lon, str(kind))
        buckets[key].append(event)

    hotspots: list[dict] = []
    for (lat, lon, kind), bucket_events in buckets.items():
        countries = sorted({event.get("country") for event in bucket_events if event.get("country")})
        deaths = sum(int(event.get("best") or 0) for event in bucket_events)
        label = bucket_events[0].get("where_coordinates") or bucket_events[0].get("country") or "Conflict hotspot"
        conflict = bucket_events[0].get("conflict_name") or bucket_events[0].get("dyad_name") or "Organized violence"
        hotspots.append(
            {
                "id": f"ucdp-{len(hotspots)+1}",
                "label": label,
                "conflict": conflict,
                "kind": f"ucdp-{kind}",
                "lat": lat,
                "lon": lon,
                "weight": min(10, 3 + len(bucket_events)),
                "countries": countries,
                "sourceUrl": "",
                "eventCount": len(bucket_events),
                "fatalities": deaths,
            }
        )

    hotspots.sort(key=lambda item: (item.get("weight", 0), item.get("fatalities", 0)), reverse=True)
    return hotspots[:120]


def build_manual_payload() -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    hotspots = []
    for hotspot in MANUAL_HOTSPOTS:
        enriched = dict(hotspot)
        market_url = hotspot.get("marketUrl")
        if market_url:
            enriched["marketCard"] = fetch_important_spots.fetch_polymarket_card(
                market_url,
                hotspot.get("marketFallback"),
            )
        hotspots.append(enriched)
    return {
        "generatedAt": generated_at,
        "provider": "manual-fallback",
        "windowDays": WINDOW_DAYS,
        "hotspots": hotspots,
    }


def build_payload() -> dict:
    env = load_env()
    token = None
    try:
        token = get_acled_token(env)
    except Exception:
        token = None

    if token:
        try:
            events = fetch_acled_events(token)
            hotspots = build_hotspots_from_acled(events)
            if hotspots:
                return {
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "provider": "acled",
                    "windowDays": WINDOW_DAYS,
                    "events": events,
                    "hotspots": hotspots,
                }
        except Exception:
            pass

    ucdp_token = env.get("UCDP_API_TOKEN")
    if ucdp_token:
        try:
            events = fetch_ucdp_events(ucdp_token)
            hotspots = build_hotspots_from_ucdp(events)
            if hotspots:
                return {
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "provider": "ucdp",
                    "windowDays": WINDOW_DAYS,
                    "events": events,
                    "hotspots": hotspots,
                }
        except Exception:
            pass

    return build_manual_payload()


def main() -> int:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload.get('hotspots', []))} conflict hotspots to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
