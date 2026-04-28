#!/usr/bin/env python3

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
MAP_PATH = ROOT / "data" / "countries-110m.json"
OUTPUT_PATH = ROOT / "data" / "generated" / "country_facts.json"

RESTCOUNTRIES_URL = "https://restcountries.com/v3.1/all?fields=name,cca3,region,subregion,altSpellings"
DEMOCRACY_EIU_URL = "https://ourworldindata.org/grapher/democracy-index-eiu.csv?download-format=tab"
POLITICAL_REGIME_URL = "https://ourworldindata.org/grapher/political-regime.csv?download-format=tab"
WORLD_BANK_GROWTH_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.PCAP.KD.ZG?format=json&per_page=25000"
ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_API_URL = "https://acleddata.com/api/acled/read"
WIKIPEDIA_CONFLICTS_URL = "https://en.wikipedia.org/wiki/List_of_ongoing_armed_conflicts"

NAME_ALIASES = {
    "United States of America": "United States",
    "Czech Republic": "Czechia",
    "Democratic Republic of the Congo": "Congo (Democratic Republic of the)",
    "Republic of the Congo": "Congo",
    "Ivory Coast": "Côte d'Ivoire",
    "Bosnia and Herzegovina": "Bosnia and Herz.",
    "North Macedonia": "Macedonia",
    "Eswatini": "Swaziland",
    "Myanmar": "Myanmar (Burma)",
    "Laos": "Lao People's Democratic Republic",
    "Russia": "Russian Federation",
    "Syria": "Syrian Arab Republic",
    "Moldova": "Moldova (Republic of)",
    "Venezuela": "Venezuela (Bolivarian Republic of)",
    "Iran": "Iran (Islamic Republic of)",
    "Tanzania": "Tanzania, United Republic of",
    "Bolivia": "Bolivia (Plurinational State of)",
    "Palestine": "Palestine, State of",
}

def curl_text(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sfL", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"curl failed for {url}")
    return result.stdout


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


def curl_json(url: str) -> object:
    return json.loads(curl_text(url))


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


def normalize_name(name: str) -> str:
    value = NAME_ALIASES.get(name, name).strip().lower()
    cleaned = []
    for char in value:
        if char.isalnum():
            cleaned.append(char)
        elif char in {" ", "-", "'", "(", ")", ",", "."}:
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


def get_map_country_names() -> list[str]:
    world = json.loads(MAP_PATH.read_text())
    geometries = world["objects"]["countries"]["geometries"]
    return [geometry["properties"]["name"] for geometry in geometries]


def build_restcountries_index() -> tuple[dict[str, dict], dict[str, str]]:
    payload = curl_json(RESTCOUNTRIES_URL)
    by_code: dict[str, dict] = {}
    by_name: dict[str, str] = {}

    for entry in payload:
        code = entry.get("cca3")
        if not code:
            continue
        by_code[code] = entry
        names = [
            entry.get("name", {}).get("common", ""),
            entry.get("name", {}).get("official", ""),
            *entry.get("altSpellings", []),
        ]
        for name in names:
            if name:
                by_name.setdefault(normalize_name(name), code)
    return by_code, by_name


def load_csv_rows(url: str) -> list[dict[str, str]]:
    text = curl_text(url)
    return list(csv.DictReader(io.StringIO(text)))


def latest_rows_by_code(rows: list[dict[str, str]], value_field: str) -> dict[str, dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        code = row.get("Code", "").strip()
        year = row.get("Year", "").strip()
        if not code or not year or not row.get(value_field):
            continue
        existing = latest.get(code)
        if existing is None or int(year) > int(existing["Year"]):
            latest[code] = row
    return latest


def fetch_latest_growth_by_code() -> dict[str, dict[str, object]]:
    payload = curl_json(WORLD_BANK_GROWTH_URL)
    if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
        raise RuntimeError("Unexpected World Bank response")

    latest: dict[str, dict[str, object]] = {}
    for row in payload[1]:
        code = str(row.get("countryiso3code") or "").strip()
        year = str(row.get("date") or "").strip()
        value = row.get("value")
        if not code or not year or value is None:
            continue
        try:
            numeric_value = float(value)
            numeric_year = int(year)
        except (TypeError, ValueError):
            continue

        existing = latest.get(code)
        if existing is None or numeric_year > int(existing["year"]):
            latest[code] = {"value": numeric_value, "year": numeric_year}
    return latest


def format_growth_value(value: float, year: int) -> str:
    return f"{value:.1f}% ({year})"


def bucket_democracy(score: float) -> str:
    if score >= 7:
        return "70+"
    if score >= 6:
        return "60-70"
    if score >= 5:
        return "50-60"
    return "<50"


def map_regime_to_bucket(value: str) -> str:
    mapping = {
        "3": "70+",
        "2": "60-70",
        "1": "<50",
        "0": "<50",
    }
    return mapping.get(value.strip(), "Pending score source")


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


def build_code_to_map_name(map_names: list[str], rest_name_index: dict[str, str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for map_name in map_names:
        code = rest_name_index.get(normalize_name(map_name))
        if code:
            mapping.setdefault(code, map_name)
    return mapping


def build_country_name_lookup(
    rest_by_code: dict[str, dict],
    code_to_map_name: dict[str, str],
) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for code, entry in rest_by_code.items():
        map_name = code_to_map_name.get(code)
        if not map_name:
            continue
        names = [
            map_name,
            entry.get("name", {}).get("common", ""),
            entry.get("name", {}).get("official", ""),
            *entry.get("altSpellings", []),
        ]
        for name in names:
            if name:
                lookup[normalize_name(name)] = map_name
    return lookup


def fetch_acled_recent_events(access_token: str) -> list[dict]:
    start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    events: list[dict] = []
    page = 1

    while True:
        params = {
            "_format": "json",
            "disorder_type": "Political violence",
            "event_date": start_date,
            "event_date_where": ">=",
            "fields": "country|event_type|fatalities|actor1|actor2",
            "limit": "5000",
            "page": str(page),
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

        rows = payload.get("data") or []
        events.extend(rows)
        if len(rows) < 5000:
            break
        page += 1

    return events


def classify_conflict_label(events: int, armed_events: int, fatalities: int) -> str:
    if armed_events >= 10 or fatalities >= 25:
        return "Active armed conflict signal"
    if events >= 3:
        return "Recent political violence signal"
    if events >= 1:
        return "Limited recent conflict signal"
    return "No recent ACLED conflict signal"


def build_acled_conflict_index(
    events: list[dict],
    country_name_lookup: dict[str, str],
) -> dict[str, str]:
    armed_types = {"Battles", "Explosions/Remote violence", "Violence against civilians"}
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"events": 0, "armed_events": 0, "fatalities": 0})

    for row in events:
        raw_name = str(row.get("country") or "").strip()
        map_name = country_name_lookup.get(normalize_name(raw_name))
        if not map_name:
            continue

        stats[map_name]["events"] += 1
        if row.get("event_type") in armed_types:
            stats[map_name]["armed_events"] += 1

        try:
            stats[map_name]["fatalities"] += int(float(row.get("fatalities") or 0))
        except (TypeError, ValueError):
            pass

    return {
        country_name: classify_conflict_label(
            values["events"],
            values["armed_events"],
            values["fatalities"],
        )
        for country_name, values in stats.items()
    }


def fetch_wikipedia_conflict_page() -> str:
    result = subprocess.run(
        ["curl", "-sfL", "--insecure", WIKIPEDIA_CONFLICTS_URL],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Wikipedia conflict page fetch failed")
    return result.stdout


def fetch_wikipedia_page(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sfL", "--insecure", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Wikipedia page fetch failed for {url}")
    return result.stdout


def split_locations(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s{2,}", value.replace("\xa0", " ")) if part.strip()]


def is_meaningful_conflict_name(value: str) -> bool:
    lowered = value.strip().lower()
    if not lowered:
        return False
    if lowered in {"current war", "during gaza war", "internal conflict during", "middle eastern crisis", "since 2016"}:
        return False
    keywords = ("war", "conflict", "insurg", "crisis", "violence", "clashes", "campaign", "attacks")
    return any(keyword in lowered for keyword in keywords)


def extract_primary_conflict_name(cell) -> str | None:
    candidates: list[tuple[str, str]] = []
    for link in cell.select("a"):
        text = link.get_text(" ", strip=True)
        if is_meaningful_conflict_name(text):
            href = link.get("href") or ""
            if href.startswith("/wiki/"):
                href = f"https://en.wikipedia.org{href}"
            candidates.append((text, href))
    return candidates[0] if candidates else None


def normalize_wikipedia_href(href: str) -> str:
    if href.startswith("/wiki/"):
        return f"https://en.wikipedia.org{href}"
    return href


def extract_mapped_countries_from_container(container, country_name_lookup: dict[str, str]) -> list[str]:
    mapped: list[str] = []
    for link in container.select("a"):
        text = link.get_text(" ", strip=True)
        map_name = country_name_lookup.get(normalize_name(text))
        if map_name and map_name not in mapped:
            mapped.append(map_name)

    if mapped:
        return mapped

    fallback_text = container.get_text(" ", strip=True)
    for candidate in split_locations(fallback_text):
        map_name = country_name_lookup.get(normalize_name(candidate))
        if map_name and map_name not in mapped:
            mapped.append(map_name)
    return mapped


def extract_conflict_sides(url: str, country_name_lookup: dict[str, str]) -> list[dict[str, object]]:
    soup = BeautifulSoup(fetch_wikipedia_page(url), "html.parser")
    infobox = soup.select_one("table.infobox")
    if not infobox:
        return []

    rows = infobox.select("tr")
    header_index = None
    for index, row in enumerate(rows):
        header = row.find("th")
        if not header:
            continue
        header_text = header.get_text(" ", strip=True).lower()
        if header_text in {"belligerents", "main belligerents", "combatants", "main combatants"}:
            header_index = index
            break

    if header_index is None:
        return []

    for row in rows[header_index + 1 :]:
        direct_cells = row.find_all("td", recursive=False)
        if len(direct_cells) < 2:
            if row.find("th"):
                break
            continue

        sides: list[dict[str, object]] = []
        for side_index, cell in enumerate(direct_cells, start=1):
            countries = extract_mapped_countries_from_container(cell, country_name_lookup)
            if not countries:
                continue
            sides.append(
                {
                    "label": f"Side {side_index}",
                    "countries": countries,
                }
            )
        if len(sides) >= 2:
            return sides

    return []


def build_wikipedia_conflict_index(country_name_lookup: dict[str, str]) -> dict[str, list[dict[str, object]]]:
    soup = BeautifulSoup(fetch_wikipedia_conflict_page(), "html.parser")
    conflict_names_by_country: dict[str, list[dict[str, object]]] = defaultdict(list)
    conflict_sides_cache: dict[str, list[dict[str, object]]] = {}

    for table in soup.select("table.wikitable")[:4]:
        rows = table.select("tr")[1:]
        for row in rows:
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) < 4:
                continue
            conflict_entry = extract_primary_conflict_name(cells[1])
            if not conflict_entry:
                continue
            conflict_name, conflict_url = conflict_entry
            locations = [link.get_text(" ", strip=True) for link in cells[3].select("a")]
            if not locations:
                locations = split_locations(cells[3].get_text(" ", strip=True))
            mapped_countries: list[str] = []
            for location in locations:
                map_name = country_name_lookup.get(normalize_name(location))
                if not map_name:
                    continue
                if map_name not in mapped_countries:
                    mapped_countries.append(map_name)

            if not mapped_countries:
                continue

            if conflict_url and conflict_url not in conflict_sides_cache:
                try:
                    conflict_sides_cache[conflict_url] = extract_conflict_sides(conflict_url, country_name_lookup)
                except Exception:
                    conflict_sides_cache[conflict_url] = []
            conflict_sides = conflict_sides_cache.get(conflict_url, [])

            for map_name in mapped_countries:
                existing_names = {entry["name"] for entry in conflict_names_by_country[map_name]}
                if conflict_name in existing_names:
                    continue
                conflict_names_by_country[map_name].append(
                    {
                        "name": conflict_name,
                        "url": conflict_url,
                        "countries": mapped_countries,
                        "sides": conflict_sides,
                    }
                )

    return {country_name: conflicts[:4] for country_name, conflicts in conflict_names_by_country.items()}


def build_facts() -> dict:
    env = load_env()
    acled_token = None
    acled_conflicts: dict[str, str] = {}
    wikipedia_conflicts: dict[str, list[dict[str, object]]] = {}
    try:
        acled_token = get_acled_token(env)
    except Exception:
        acled_token = None

    map_names = get_map_country_names()
    rest_by_code, rest_name_index = build_restcountries_index()
    code_to_map_name = build_code_to_map_name(map_names, rest_name_index)
    country_name_lookup = build_country_name_lookup(rest_by_code, code_to_map_name)
    democracy_rows = latest_rows_by_code(load_csv_rows(DEMOCRACY_EIU_URL), "Democracy Index")
    regime_rows = latest_rows_by_code(load_csv_rows(POLITICAL_REGIME_URL), "Political regime")
    growth_rows = fetch_latest_growth_by_code()

    if acled_token:
        try:
            acled_events = fetch_acled_recent_events(acled_token)
            acled_conflicts = build_acled_conflict_index(acled_events, country_name_lookup)
        except Exception:
            acled_conflicts = {}
    if not acled_conflicts:
        try:
            wikipedia_conflicts = build_wikipedia_conflict_index(country_name_lookup)
        except Exception:
            wikipedia_conflicts = {}

    countries: dict[str, dict] = {}
    generated_at = datetime.now(timezone.utc).isoformat()

    for map_name in map_names:
        code = rest_name_index.get(normalize_name(map_name))
        entry = rest_by_code.get(code, {})
        region = entry.get("subregion") or entry.get("region") or "Region not loaded"

        democracy_index = "Pending score source"
        democracy_row = democracy_rows.get(code or "")
        if democracy_row:
            try:
                democracy_index = bucket_democracy(float(democracy_row["Democracy Index"]))
            except ValueError:
                democracy_index = "Pending score source"
        else:
            regime_row = regime_rows.get(code or "")
            if regime_row:
                democracy_index = map_regime_to_bucket(regime_row["Political regime"])

        countries[map_name] = {
            "region": region,
            "democracyIndex": democracy_index,
            "economicGrowth": "No recent World Bank data",
            "economicGrowthValue": None,
            "economicGrowthYear": None,
            "conflict": acled_conflicts.get(map_name, "No live conflict listing"),
            "conflicts": wikipedia_conflicts.get(map_name, []),
            "factsUpdatedAt": generated_at,
        }
        growth_row = growth_rows.get(code or "")
        if growth_row:
            countries[map_name]["economicGrowth"] = format_growth_value(
                float(growth_row["value"]),
                int(growth_row["year"]),
            )
            countries[map_name]["economicGrowthValue"] = round(float(growth_row["value"]), 3)
            countries[map_name]["economicGrowthYear"] = int(growth_row["year"])
        if countries[map_name]["conflicts"]:
            conflict_names = [entry["name"] for entry in countries[map_name]["conflicts"]]
            countries[map_name]["conflict"] = f"Involved in: {', '.join(conflict_names)}"

    return {
        "generatedAt": generated_at,
        "countries": countries,
    }


def main() -> int:
    payload = build_facts()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['countries'])} country facts to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
