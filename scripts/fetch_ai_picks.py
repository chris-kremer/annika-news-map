#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_briefings


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
OUTPUT_PATH = ROOT / "data" / "generated" / "ai_picks.json"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
THE_NEWS_ENDPOINT = "https://api.thenewsapi.com/v1/news/top"
RELIEFWEB_ENDPOINT = "https://api.reliefweb.int/v2/reports"
OPENAI_RESPONSES_ENDPOINT = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5-nano"
SELECTION_PRINCIPLE = "International stories with cross-border stakes that are easy to miss, avoiding obvious week-long headline cycles unless there is a fresh, specific angle."

DISCOVERY_QUERIES = [
    {
        "id": "power-security-shocks",
        "query": '(coup OR junta OR mutiny OR "military takeover" OR "state of emergency" OR gangs OR cartel OR "organized crime" OR curfew)',
        "category": "Power and security shock",
    },
    {
        "id": "cross-border-flashpoints",
        "query": '("border clashes" OR "cross-border" OR incursion OR blockade OR "missile strike" OR "naval drills" OR sanctions OR "export controls" OR shipping)',
        "category": "Cross-border flashpoint",
    },
    {
        "id": "human-system-stress",
        "query": '(refugees OR displacement OR "aid access" OR famine OR "food security" OR drought OR blackout OR hydropower OR "fuel shortage" OR protests OR "constitutional crisis")',
        "category": "Human and system stress",
    },
]

RSS_FEEDS = [
    {
        "id": "reuters-world",
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "category": "Global wire",
    },
    {
        "id": "aljazeera-world",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "category": "Global wire",
    },
    {
        "id": "bbc-world",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "Global wire",
    },
]

DISCOVERY_FORBIDDEN_TERMS = {
    "analysis:",
    "bowen:",
    "footballer",
    "fudbaler",
    "guide",
    "hashish",
    "hašiš",
    "map of",
    "mapped",
    "commodity",
    "explainer",
    "resource wealth",
    "mapping mali",
    "what is",
    "why ",
}

DISCOVERY_REQUIRED_TERMS = {
    "aid",
    "army",
    "attack",
    "attacks",
    "blackout",
    "blockade",
    "border",
    "cartel",
    "ceasefire",
    "clashes",
    "conflict",
    "coup",
    "cruise ship",
    "curfew",
    "displacement",
    "drought",
    "emergency",
    "export controls",
    "famine",
    "food security",
    "gang",
    "gangs",
    "hormuz",
    "humanitarian",
    "incursion",
    "junta",
    "missile",
    "military",
    "no-confidence",
    "ousted",
    "outbreak",
    "naval",
    "protests",
    "refugee",
    "refugees",
    "sanctions",
    "shipping",
    "standoff",
    "strike",
    "strikes",
    "succession",
    "trade war",
    "transport workers",
}

DISCOVERY_GENERIC_TERMS = {
    "holds talks",
    "held talks",
    "what kim",
    "outfits tell us",
    "raises risk",
}

DISCOVERY_KEY_AREA_TERMS = {
    "hormuz": "hormuz",
    "strait of hormuz": "hormuz",
}

DISCOVERY_STRONG_PATTERNS = {
    "no-confidence": 0.2,
    "ousted": 0.16,
    "transport workers": 0.18,
    "fuel": 0.08,
    "outbreak": 0.18,
    "cruise ship": 0.14,
    "succession": 0.12,
}


COUNTRY_COORDINATES = {
    "Chad": (15.4542, 18.7322),
    "Ecuador": (-1.8312, -78.1834),
    "Mali": (17.5707, -3.9962),
    "Mexico": (23.6345, -102.5528),
    "Serbia": (44.0165, 21.0059),
    "Sudan": (12.8628, 30.2176),
    "Lebanon": (33.8547, 35.8623),
    "Iran": (32.4279, 53.688),
    "Israel": (31.0461, 34.8516),
    "Nigeria": (9.082, 8.6753),
    "Democratic Republic of the Congo": (-4.0383, 21.7587),
    "Indonesia": (-2.5489, 118.0149),
    "Haiti": (18.9712, -72.2852),
    "Afghanistan": (33.9391, 67.71),
    "Bolivia": (-16.2902, -63.5887),
    "North Korea": (40.3399, 127.5101),
    "Pakistan": (30.3753, 69.3451),
    "Romania": (45.9432, 24.9668),
    "Spain": (40.4168, -3.7038),
    "Ukraine": (48.3794, 31.1656),
    "Zambia": (-13.1339, 27.8493),
}

LOCATION_COORDINATES = {
    "Canary Islands, Spain": (28.2916, -16.6291),
}

try:
    import certifi
except ImportError:
    certifi = None

SSL_CONTEXT = (
    ssl.create_default_context(cafile=certifi.where())
    if certifi
    else ssl.create_default_context()
)

UNDERLOOKED_STORY_DESK = [
    {
        "id": "mali-coordinated-attacks",
        "query": '(Mali OR Bamako) ("coordinated attacks" OR JNIM OR Azawad OR coup)',
        "fallbackTitle": "Mali's late-April attacks look bigger than a routine insurgent flare-up",
        "summary": "Coordinated attacks around Bamako and several regional cities put pressure on Mali's junta and its Russian-backed security model.",
        "whyItMatters": "This is the kind of Sahel story that can move fast without leading global homepages: a capital-security shock, junta legitimacy, rebel-jihadist coordination, and spillover risk for Niger and Burkina Faso.",
        "angle": "Fresh capital-security shock after coordinated nationwide attacks.",
        "freshness": "New escalation",
        "place": "Bamako, Mali",
        "country": "Mali",
        "region": "West Africa",
        "category": "Underlooked conflict",
        "lat": 12.6392,
        "lon": -8.0029,
        "importance": 0.9,
        "overlap": [{"type": "ongoing-conflict", "label": "Sahel instability"}],
        "sources": [
            {
                "title": "Gunmen stage simultaneous attacks across Mali, army says",
                "url": "https://www.aljazeera.com/news/2026/4/25/mali-army-says-armed-groups-launch-nationwide-attacks-gunfire-near-airport",
            }
        ],
    },
    {
        "id": "ecuador-curfew-gangs",
        "query": '(Ecuador OR Guayaquil OR Quito) (curfew OR gangs OR "state of emergency" OR violence)',
        "fallbackTitle": "Ecuador extends curfews as gang violence becomes a governance problem",
        "summary": "A fresh curfew across nine provinces shows Ecuador's security emergency is no longer just a crime story; it is shaping daily economic life and state capacity.",
        "whyItMatters": "Ecuador rarely stays in the international top slot, but the combination of ports, cocaine routes, emergency rule, and economic disruption makes this a strategic Latin America watch item.",
        "angle": "Gang pressure is forcing emergency governance across major provinces.",
        "freshness": "Fresh policy move",
        "place": "Guayaquil / Quito, Ecuador",
        "country": "Ecuador",
        "region": "South America",
        "category": "Organized crime",
        "lat": -2.19,
        "lon": -79.889,
        "importance": 0.84,
        "overlap": [],
        "sources": [
            {
                "title": "Noboa decreta 15 días de toque de queda en nueve provincias",
                "url": "https://elpais.com/america/2026-05-02/noboa-decreta-15-dias-de-toque-de-queda-en-nueve-provincias-y-reaviva-el-choque-con-los-sectores-productivos.html",
            }
        ],
    },
    {
        "id": "haiti-gang-territory",
        "query": '(Haiti OR "Port-au-Prince") (gangs OR "territory controlled" OR "Viv ansanm")',
        "fallbackTitle": "Haiti's gang map is shifting, but armed groups still dominate the capital",
        "summary": "Local police leadership says gangs control less of metropolitan Port-au-Prince than before, yet the reported 72% figure still points to a capital where armed groups shape movement, services, and politics.",
        "whyItMatters": "The interesting part is not simply that Haiti is violent; it is whether small territorial reversals change the balance before the international security mission winds down.",
        "angle": "A granular update on territorial control, not another generic Haiti-is-in-crisis card.",
        "freshness": "Recent local update",
        "place": "Port-au-Prince, Haiti",
        "country": "Haiti",
        "region": "Caribbean",
        "category": "State capacity",
        "lat": 18.5944,
        "lon": -72.3074,
        "importance": 0.8,
        "overlap": [],
        "sources": [
            {
                "title": "PNH Chief Says Gangs Control 72% of Metropolitan Area",
                "url": "https://lenouvelliste.com/en/article/266079/les-gangs-controlent-72-de-la-zone-metropolitaine-selon-le-directeur-general-de-la-pnh",
            }
        ],
    },
    {
        "id": "southern-africa-drought",
        "query": '("Southern Africa" OR Zambia OR Malawi OR Zimbabwe) (drought OR hydropower OR food security)',
        "fallbackTitle": "Southern Africa's drought is turning into a power, food, and budget story",
        "summary": "Drought pressure across parts of Southern Africa keeps showing up as hydropower shortages, food insecurity, and fiscal strain rather than one dramatic breaking-news event.",
        "whyItMatters": "Slow disasters are easy to miss. This one matters because electricity, crops, debt, and migration pressure can reinforce each other across borders.",
        "angle": "Slow-moving drought effects that compound across energy and food systems.",
        "freshness": "Slow-burn risk",
        "place": "Lusaka, Zambia",
        "country": "Zambia / Southern Africa",
        "region": "Southern Africa",
        "category": "Climate stress",
        "lat": -15.3875,
        "lon": 28.3228,
        "importance": 0.73,
        "overlap": [],
        "sources": [
            {
                "title": "Southern Africa drought monitoring query",
                "url": "https://reliefweb.int/disasters?advanced-search=%28D48535%29_%28F10%29",
            }
        ],
    },
    {
        "id": "chad-sudan-spillover",
        "query": '(Chad OR "N Djamena" OR Adre) (Sudan OR refugees OR border OR Darfur)',
        "fallbackTitle": "Chad is the overlooked pressure valve for Sudan's war",
        "summary": "The Chad-Sudan border is carrying refugee flows, cross-border security risk, and political strain that rarely gets separated from the broader Sudan war headline.",
        "whyItMatters": "If Sudan is already on the conflict layer, Chad is the adjacent-system story: where displacement, aid access, and Sahel politics turn a war into a regional stress test.",
        "angle": "The neighboring-country effects of a major conflict.",
        "freshness": "Conflict spillover",
        "place": "Adre / N'Djamena, Chad",
        "country": "Chad",
        "region": "Central Africa",
        "category": "Conflict spillover",
        "lat": 12.1348,
        "lon": 15.0557,
        "importance": 0.71,
        "overlap": [{"type": "ongoing-conflict", "label": "Sudan war"}],
        "sources": [
            {
                "title": "Chad-Sudan border monitoring query",
                "url": "https://reliefweb.int/country/tcd",
            }
        ],
    },
]


def fetch_gdelt(query: str, limit: int, window_hours: int) -> list[dict]:
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(limit),
        "timespan": f"{window_hours}hours",
    }
    url = f"{GDELT_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = fetch_briefings.curl_json(url)
    return payload.get("articles", [])


def fetch_url_json(url: str) -> dict:
    request = urllib.request.Request(url, headers=fetch_briefings.REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_url_text(url: str) -> str:
    request = urllib.request.Request(url, headers=fetch_briefings.REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
        return response.read().decode("utf-8", "ignore")


def fetch_thenews_discovery(query: str, api_token: str, limit: int, window_hours: int) -> list[dict]:
    params = {
        "api_token": api_token,
        "search": query,
        "search_fields": "title,description,keywords",
        "published_after": (datetime.now(timezone.utc) - timedelta(hours=window_hours)).strftime("%Y-%m-%d"),
        "language": "en",
        "sort": "published_at",
        "limit": str(limit),
    }
    url = f"{THE_NEWS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = fetch_url_json(url)
    return payload.get("data", [])


def fetch_reliefweb(query: str, limit: int) -> list[dict]:
    params = {
        "appname": "pumpkin-news",
        "query[value]": query,
        "query[operator]": "OR",
        "limit": str(limit),
        "sort[]": "date:desc",
        "profile": "list",
    }
    url = f"{RELIEFWEB_ENDPOINT}?{urllib.parse.urlencode(params)}"
    payload = fetch_url_json(url)
    return payload.get("data", [])


def fetch_rss(feed: dict, limit: int) -> list[dict]:
    text = fetch_url_text(feed["url"])
    root = ET.fromstring(text)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date = item.findtext("pubDate") or ""
        if title:
            items.append(
                {
                    "title": title,
                    "url": link,
                    "domain": feed["id"],
                    "seendate": pub_date,
                }
            )
    return items


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def source_from_article(article: dict) -> dict:
    domain = article.get("domain") or "GDELT"
    title = " ".join(str(article.get("title") or "").split()) or f"Recent coverage from {domain}"
    return {
        "title": title,
        "url": article.get("url") or "",
    }


def normalize_text_for_quality(value: str) -> str:
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u00a0": " ",
    }
    text = str(value or "")
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def discovery_candidate(query_config: dict, article: dict, index: int) -> dict:
    domain = article.get("domain") or article.get("source", "Discovery")
    title = normalize_text_for_quality(article.get("title") or "")
    if not title:
        return {}
    return {
        "id": f"candidate-{query_config['id']}-{index}",
        "title": title,
        "url": article.get("url") or "",
        "domain": domain,
        "sourceCountry": article.get("sourcecountry") or "",
        "language": article.get("language") or "",
        "seenDate": article.get("seendate") or article.get("published_at") or "",
        "queryCategory": query_config["category"],
        "matchedQuery": query_config["query"],
        "provider": article.get("provider") or query_config.get("provider") or "GDELT",
    }


def score_candidate(candidate: dict) -> tuple[float, list[str]]:
    title = normalize_text_for_quality(candidate.get("title", ""))
    text = " ".join(
        [
            title,
            str(candidate.get("queryCategory", "")),
            str(candidate.get("domain", "")),
            str(candidate.get("provider", "")),
        ]
    ).lower()
    score = 0.0
    reasons: list[str] = []
    if not title:
        return 0.0, ["missing title"]
    if not title.isascii():
        score -= 0.4
        reasons.append("non-ascii title")
    matched_terms = sorted(term for term in DISCOVERY_REQUIRED_TERMS if term in text)
    if matched_terms:
        score += min(0.45, 0.12 * len(matched_terms))
        reasons.append("matched: " + ", ".join(matched_terms[:4]))
    else:
        score -= 0.35
        reasons.append("no required story-type terms")
    forbidden_terms = sorted(term for term in DISCOVERY_FORBIDDEN_TERMS if term in text)
    if forbidden_terms:
        score -= 0.5
        reasons.append("forbidden: " + ", ".join(forbidden_terms[:3]))
    generic_terms = sorted(term for term in DISCOVERY_GENERIC_TERMS if term in text)
    if generic_terms:
        score -= 0.22
        reasons.append("generic: " + ", ".join(generic_terms[:3]))
    strong_matches = [term for term, boost in DISCOVERY_STRONG_PATTERNS.items() if term in text]
    if strong_matches:
        boost = min(0.35, sum(DISCOVERY_STRONG_PATTERNS[term] for term in strong_matches))
        score += boost
        reasons.append("boost: " + ", ".join(strong_matches[:4]))
    key_areas = sorted({label for term, label in DISCOVERY_KEY_AREA_TERMS.items() if term in text})
    if key_areas:
        score += 0.08
        reasons.append("key-area match: " + ", ".join(key_areas))
    provider = candidate.get("provider", "")
    if provider in {"The News API", "ReliefWeb"}:
        score += 0.15
        reasons.append(f"provider: {provider}")
    elif provider == "GDELT":
        score += 0.05
        reasons.append("provider: GDELT")
    elif provider == "RSS" and "aljazeera" in str(candidate.get("domain", "")).lower():
        score -= 0.04
        reasons.append("source caution: Al Jazeera RSS")
    if safe_external_url(candidate.get("url", "")):
        score += 0.05
    else:
        reasons.append("missing url")
    return max(0.0, min(1.0, score)), reasons


def safe_external_url(value: str) -> str:
    url = str(value or "").strip()
    return url if url.lower().startswith(("http://", "https://")) else ""


def preview_discovery(args: argparse.Namespace) -> dict:
    candidates = discover_candidates(args)
    scored = []
    for candidate in candidates:
        score, reasons = score_candidate(candidate)
        scored.append({**candidate, "qualityScore": score, "qualityReasons": reasons})
    scored.sort(key=lambda item: item["qualityScore"], reverse=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "selectionPrinciple": SELECTION_PRINCIPLE,
        "candidateCount": len(candidates),
        "candidates": scored[: args.preview_limit],
    }


def story_fingerprint(value: str) -> str:
    text = normalize_text_for_quality(value).lower()
    for token in [" - ", ":", ",", ".", "'", '"', "’", "‘", "“", "”"]:
        text = text.replace(token, " ")
    stopwords = {
        "a",
        "after",
        "ahead",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "says",
        "the",
        "to",
        "with",
    }
    words = [word for word in text.split() if len(word) > 2 and word not in stopwords]
    return " ".join(words[:8])


def candidate_to_pick(candidate: dict) -> dict | None:
    score, reasons = score_candidate(candidate)
    title = normalize_text_for_quality(candidate.get("title", ""))
    if not title or not title.isascii():
        return None
    text = title.lower()
    country_hints = {
        "afghanistan": ("Afghanistan", "Afghanistan", "South Asia"),
        "pakistan": ("Pakistan", "Pakistan", "South Asia"),
        "bolivia": ("Bolivia", "Bolivia", "South America"),
        "canary islands": ("Spain", "Canary Islands, Spain", "Europe"),
        "chad": ("Chad", "Lake Chad region", "Central Africa"),
        "ecuador": ("Ecuador", "Ecuador", "South America"),
        "iran": ("Iran", "Iran", "Middle East"),
        "lebanon": ("Lebanon", "Lebanon", "Middle East"),
        "lebanese": ("Lebanon", "Lebanon", "Middle East"),
        "israel": ("Israel", "Israel", "Middle East"),
        "israeli": ("Israel", "Israel", "Middle East"),
        "mali": ("Mali", "Mali", "West Africa"),
        "kim ju ae": ("North Korea", "North Korea", "East Asia"),
        "nigeria": ("Nigeria", "Nigeria", "West Africa"),
        "nigerian": ("Nigeria", "Nigeria", "West Africa"),
        "north korea": ("North Korea", "North Korea", "East Asia"),
        "romania": ("Romania", "Romania", "Europe"),
        "russia": ("Ukraine", "Ukraine", "Europe"),
        "sudan": ("Sudan", "Sudan", "Northeast Africa"),
        "ukraine": ("Ukraine", "Ukraine", "Europe"),
    }
    has_country_hint = any(hint in text for hint in country_hints)
    has_required_term = any(term in text for term in DISCOVERY_REQUIRED_TERMS)
    is_north_korea_succession = "succession" in text and ("north korea" in text or "kim ju ae" in text)
    if score < 0.25 and not is_north_korea_succession and not (score >= 0.12 and has_country_hint and has_required_term):
        return None
    if any(term in text for term in DISCOVERY_FORBIDDEN_TERMS):
        return None

    country = ""
    place = ""
    region = ""
    lat = 0.0
    lon = 0.0
    for hint, values in country_hints.items():
        if hint in text:
            country, place, region = values
            break
    if not country:
        return None
    if place in LOCATION_COORDINATES:
        lat, lon = LOCATION_COORDINATES[place]
    elif country in COUNTRY_COORDINATES:
        lat, lon = COUNTRY_COORDINATES[country]
    else:
        return None

    category = str(candidate.get("queryCategory") or "Discovered story")
    reason_label = reasons[0] if reasons else category
    return {
        "id": f"{candidate['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "title": title,
        "summary": f"Discovery candidate from {candidate.get('domain', 'news coverage')}.",
        "whyItMatters": reason_label,
        "angle": category,
        "freshness": "Fresh",
        "lat": lat,
        "lon": lon,
        "place": place,
        "country": country,
        "region": region,
        "category": category,
        "importance": min(0.95, max(0.45, score)),
        "confidence": min(0.9, max(0.45, score)),
        "overlap": [],
        "provider": candidate.get("provider", "Discovery"),
        "storyKey": story_fingerprint(title),
        "sources": [{"title": title, "url": candidate.get("url", "")}],
    }


def dedupe_picks(picks: list[dict]) -> list[dict]:
    seen_keys = set()
    deduped = []
    for pick in picks:
        source_url = ""
        sources = pick.get("sources")
        if isinstance(sources, list) and sources:
            source_url = str(sources[0].get("url", "")).strip().lower()
        key = source_url or str(pick.get("storyKey") or pick.get("title") or "").strip().lower()
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(pick)
    return deduped


def build_pick(config: dict, articles: list[dict]) -> dict:
    sources = [source_from_article(article) for article in articles[:2]]
    if not sources:
        sources = config.get("sources", [])
    return {
        "id": f"{config['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "title": sources[0]["title"] if articles and sources else config["fallbackTitle"],
        "summary": config["summary"],
        "whyItMatters": config["whyItMatters"],
        "angle": config["angle"],
        "freshness": config["freshness"],
        "lat": config["lat"],
        "lon": config["lon"],
        "place": config["place"],
        "country": config["country"],
        "region": config["region"],
        "category": config["category"],
        "importance": config["importance"],
        "confidence": 0.78 if articles else 0.66,
        "overlap": config.get("overlap", []),
        "sources": sources,
    }


def openai_text_from_response(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(str(content["text"]))
    return "\n".join(chunks).strip()


def extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            return json.loads(stripped[start : end + 1])
        raise


def clean_model_pick(raw_pick: dict, fallback_by_id: dict[str, dict]) -> dict | None:
    raw_id = str(raw_pick.get("id", "")).strip()
    fallback = fallback_by_id.get(raw_id)
    if not fallback:
        return None

    cleaned = dict(fallback)
    for key in ["title", "summary", "whyItMatters", "angle", "freshness", "category"]:
        value = str(raw_pick.get(key, "")).strip()
        if value:
            cleaned[key] = value

    for key in ["importance", "confidence"]:
        try:
            value = float(raw_pick.get(key))
        except (TypeError, ValueError):
            continue
        cleaned[key] = max(0.0, min(1.0, value))

    sources = raw_pick.get("sources")
    if isinstance(sources, list) and sources:
        cleaned_sources = []
        for source in sources[:3]:
            if not isinstance(source, dict):
                continue
            title = str(source.get("title", "")).strip()
            url = str(source.get("url", "")).strip()
            if title or url:
                cleaned_sources.append({"title": title or cleaned["title"], "url": url})
        if cleaned_sources:
            cleaned["sources"] = cleaned_sources
    return cleaned


def clean_discovery_pick(raw_pick: dict, candidate_by_id: dict[str, dict]) -> dict | None:
    raw_id = str(raw_pick.get("id", "")).strip()
    candidate = candidate_by_id.get(raw_id)
    if not candidate:
        return None
    candidate_score, _ = score_candidate(candidate)
    if candidate_score < 0.25:
        return None

    try:
        lat = float(raw_pick.get("lat"))
        lon = float(raw_pick.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    title = normalize_text_for_quality(raw_pick.get("title") or candidate["title"])
    place = normalize_text_for_quality(raw_pick.get("place", ""))
    country = normalize_text_for_quality(raw_pick.get("country", ""))
    summary = normalize_text_for_quality(raw_pick.get("summary", ""))
    why_it_matters = normalize_text_for_quality(raw_pick.get("whyItMatters", ""))
    if not (title and place and country and summary and why_it_matters):
        return None
    combined_text = " ".join([title, summary, why_it_matters, str(raw_pick.get("angle", ""))]).lower()
    if any(term in combined_text for term in DISCOVERY_FORBIDDEN_TERMS):
        return None
    if not (str(raw_pick.get("sourceTitle", "")).isascii() and title.isascii()):
        return None

    try:
        importance = float(raw_pick.get("importance", 0.6))
    except (TypeError, ValueError):
        importance = 0.6
    try:
        confidence = float(raw_pick.get("confidence", 0.55))
    except (TypeError, ValueError):
        confidence = 0.55

    source_title = normalize_text_for_quality(raw_pick.get("sourceTitle") or candidate["title"])
    if not source_title.isascii():
        return None
    coord_country = country.split("/")[0].replace(" and ", "/").split("/")[0].strip()
    has_specific_coordinates = not (abs(lat) < 0.001 and abs(lon) < 0.001)
    if place in LOCATION_COORDINATES:
        lat, lon = LOCATION_COORDINATES[place]
    elif not has_specific_coordinates and coord_country in COUNTRY_COORDINATES:
        lat, lon = COUNTRY_COORDINATES[coord_country]
    elif not has_specific_coordinates:
        return None
    return {
        "id": f"{raw_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "title": title,
        "summary": summary,
        "whyItMatters": why_it_matters,
        "angle": str(raw_pick.get("angle") or candidate["queryCategory"]).strip(),
        "freshness": str(raw_pick.get("freshness") or "Fresh development").strip(),
        "lat": lat,
        "lon": lon,
        "place": place,
        "country": country,
        "region": str(raw_pick.get("region") or "").strip(),
        "category": str(raw_pick.get("category") or candidate["queryCategory"]).strip(),
        "importance": max(0.0, min(1.0, importance)),
        "confidence": max(0.0, min(1.0, confidence)),
        "overlap": [],
        "provider": candidate.get("provider", "Discovery"),
        "sources": [{"title": source_title or title, "url": candidate.get("url", "")}],
    }


def add_candidate(candidates: list[dict], seen_urls: set[str], seen_titles: set[str], query_config: dict, article: dict) -> None:
    candidate = discovery_candidate(query_config, article, len(candidates))
    if not candidate:
        return
    url_key = candidate["url"].strip().lower()
    title_key = candidate["title"].strip().lower()
    if (url_key and url_key in seen_urls) or title_key in seen_titles:
        return
    if url_key:
        seen_urls.add(url_key)
    seen_titles.add(title_key)
    candidates.append(candidate)


def discover_candidates(args: argparse.Namespace) -> list[dict]:
    env = load_env()
    candidates = []
    seen_urls = set()
    seen_titles = set()

    if not args.skip_gdelt:
        for query_index, query_config in enumerate(DISCOVERY_QUERIES):
            if query_index:
                time.sleep(args.delay_seconds)
            try:
                articles = fetch_gdelt(query_config["query"], args.discovery_per_query, args.window_hours)
            except Exception as error:
                print(f"warning: discovery query {query_config['id']} failed: {error}", file=sys.stderr)
                continue
            provider_config = {**query_config, "provider": "GDELT"}
            for article in articles:
                add_candidate(candidates, seen_urls, seen_titles, provider_config, article)

    api_token = env.get("THE_NEWS_API_TOKEN", "").strip()
    if api_token:
        for query_index, query_config in enumerate(DISCOVERY_QUERIES):
            if candidates and query_index:
                time.sleep(min(args.delay_seconds, 1.0))
            try:
                articles = fetch_thenews_discovery(
                    query_config["query"],
                    api_token,
                    args.secondary_per_query,
                    args.window_hours,
                )
            except Exception as error:
                print(f"warning: The News API discovery query {query_config['id']} failed: {error}", file=sys.stderr)
                continue
            provider_config = {**query_config, "provider": "The News API"}
            for article in articles:
                normalized = {
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "domain": article.get("domain", "The News API"),
                    "published_at": article.get("published_at", ""),
                    "provider": "The News API",
                }
                add_candidate(candidates, seen_urls, seen_titles, provider_config, normalized)

    relief_queries = [
        {"id": "reliefweb-humanitarian", "query": "refugees displacement food security drought aid access", "category": "Human security", "provider": "ReliefWeb"},
        {"id": "reliefweb-conflict", "query": "conflict border attacks humanitarian access", "category": "Human security", "provider": "ReliefWeb"},
    ]
    for query_config in relief_queries:
        try:
            articles = fetch_reliefweb(query_config["query"], args.secondary_per_query)
        except Exception as error:
            print(f"warning: ReliefWeb discovery query {query_config['id']} failed: {error}", file=sys.stderr)
            continue
        for article in articles:
            fields = article.get("fields", {})
            normalized = {
                "title": fields.get("title", ""),
                "url": fields.get("url", ""),
                "domain": "reliefweb.int",
                "published_at": fields.get("date", {}).get("created", ""),
                "provider": "ReliefWeb",
            }
            add_candidate(candidates, seen_urls, seen_titles, query_config, normalized)

    if not args.skip_rss:
        for feed in RSS_FEEDS:
            try:
                articles = fetch_rss(feed, args.rss_per_feed)
            except Exception as error:
                print(f"warning: RSS feed {feed['id']} failed: {error}", file=sys.stderr)
                continue
            query_config = {
                "id": feed["id"],
                "query": feed["url"],
                "category": feed["category"],
                "provider": "RSS",
            }
            for article in articles:
                article["provider"] = "RSS"
                add_candidate(candidates, seen_urls, seen_titles, query_config, article)
    return candidates


def curate_discovery_with_openai(candidates: list[dict], limit: int, env: dict[str, str]) -> list[dict]:
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key or not candidates:
        return []

    model = env.get("OPENAI_AI_PICKS_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    prompt_payload = {
        "selectionPrinciple": SELECTION_PRINCIPLE,
        "task": "Select underlooked global developments from broad news-search candidates.",
        "requirements": [
            "Pick developments of the same type as coups, gang pressure on governance, border flashpoints, sanctions shocks, displacement, aid access, energy/food stress, election instability, or other cross-border state-capacity risks.",
            "The geography can be anywhere. Do not favor the seeded fallback countries.",
            "Prefer fresh, specific developments over generic ongoing crisis summaries.",
            "Use only supplied candidate articles as sources. Do not invent source URLs.",
            "Prefer corroborated or high-signal candidates from GDELT, The News API, ReliefWeb, or reputable RSS feeds; reject routine commodity, sports, celebrity, and domestic-crime items unless there are explicit state-capacity or cross-border security stakes.",
            "You may infer the best map place and approximate coordinates only when the article title clearly identifies a place or country.",
            "Skip any candidate whose place cannot be reasonably identified from the supplied data.",
            "Return all pick titles and source titles in English ASCII only.",
        ],
        "outputShape": {
            "picks": [
                {
                    "id": "candidate id",
                    "title": "specific concise title",
                    "summary": "one sentence",
                    "whyItMatters": "one sentence on cross-border stakes",
                    "angle": "fresh editorial angle",
                    "freshness": "short label",
                    "category": "short category",
                    "place": "city/region, country",
                    "country": "country",
                    "region": "world region",
                    "lat": "number",
                    "lon": "number",
                    "importance": "0.0-1.0",
                    "confidence": "0.0-1.0",
                    "sourceTitle": "English source headline",
                }
            ]
        },
        "candidates": candidates,
        "limit": limit,
    }
    body = {
        "model": model,
        "instructions": "You are the Pumpkin News assignment editor. Return valid JSON only.",
        "input": json.dumps(prompt_payload, ensure_ascii=False),
        "max_output_tokens": 9000,
        "reasoning": {"effort": "minimal"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "discovered_ai_picks",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "whyItMatters": {"type": "string"},
                                    "angle": {"type": "string"},
                                    "freshness": {"type": "string"},
                                    "category": {"type": "string"},
                                    "place": {"type": "string"},
                                    "country": {"type": "string"},
                                    "region": {"type": "string"},
                                    "lat": {"type": "number"},
                                    "lon": {"type": "number"},
                                    "importance": {"type": "number"},
                                    "confidence": {"type": "number"},
                                    "sourceTitle": {"type": "string"},
                                },
                                "required": [
                                    "id",
                                    "title",
                                    "summary",
                                    "whyItMatters",
                                    "angle",
                                    "freshness",
                                    "category",
                                    "place",
                                    "country",
                                    "region",
                                    "lat",
                                    "lon",
                                    "importance",
                                    "confidence",
                                    "sourceTitle",
                                ],
                            },
                        }
                    },
                    "required": ["picks"],
                },
            }
        },
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        payload = json.loads(response.read().decode("utf-8"))

    model_payload = extract_json_object(openai_text_from_response(payload))
    raw_picks = model_payload.get("picks", [])
    if not isinstance(raw_picks, list):
        raise RuntimeError("OpenAI response did not include a picks array")

    candidate_by_id = {candidate["id"]: candidate for candidate in candidates}
    curated = []
    seen_sources = set()
    for raw_pick in raw_picks:
        if not isinstance(raw_pick, dict):
            continue
        cleaned = clean_discovery_pick(raw_pick, candidate_by_id)
        if not cleaned:
            continue
        source_url = cleaned["sources"][0].get("url", "").strip().lower()
        if source_url and source_url in seen_sources:
            continue
        if source_url:
            seen_sources.add(source_url)
        curated.append(cleaned)
    return curated


def curate_with_openai(picks: list[dict], limit: int, env: dict[str, str]) -> list[dict]:
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return picks

    model = env.get("OPENAI_AI_PICKS_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    prompt_payload = {
        "selectionPrinciple": SELECTION_PRINCIPLE,
        "requirements": [
            "Return the most interesting underlooked international picks, ranked by importance.",
            "Prefer fresh specific angles over generic week-long headline cycles.",
            "Do not invent facts, places, URLs, or sources. Use only the candidate data.",
            "Return all pick titles and source titles in English. If a source headline is not English, translate the headline into natural English and keep the original URL.",
            "If a pick overlaps an ongoing conflict or key area, preserve its overlap field.",
            "Keep coordinates unchanged so markers remain correctly placed on the globe.",
        ],
        "outputShape": {
            "picks": [
                {
                    "id": "candidate id",
                    "title": "specific, concise title",
                    "summary": "one sentence",
                    "whyItMatters": "one sentence on cross-border stakes",
                    "angle": "fresh editorial angle",
                    "freshness": "short label",
                    "category": "short category",
                    "importance": "0.0-1.0",
                    "confidence": "0.0-1.0",
                    "sources": [{"title": "source title", "url": "source URL"}],
                }
            ]
        },
        "candidates": picks,
        "limit": limit,
    }
    body = {
        "model": model,
        "instructions": "You are the Pumpkin News assignment editor. Return valid JSON only.",
        "input": json.dumps(prompt_payload, ensure_ascii=False),
        "max_output_tokens": 6000,
        "reasoning": {"effort": "minimal"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ai_picks",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "id": {"type": "string"},
                                    "title": {"type": "string"},
                                    "summary": {"type": "string"},
                                    "whyItMatters": {"type": "string"},
                                    "angle": {"type": "string"},
                                    "freshness": {"type": "string"},
                                    "category": {"type": "string"},
                                    "importance": {"type": "number"},
                                    "confidence": {"type": "number"},
                                    "sources": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "title": {"type": "string"},
                                                "url": {"type": "string"},
                                            },
                                            "required": ["title", "url"],
                                        },
                                    },
                                },
                                "required": [
                                    "id",
                                    "title",
                                    "summary",
                                    "whyItMatters",
                                    "angle",
                                    "freshness",
                                    "category",
                                    "importance",
                                    "confidence",
                                    "sources",
                                ],
                            },
                        }
                    },
                    "required": ["picks"],
                },
            }
        },
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
        payload = json.loads(response.read().decode("utf-8"))

    model_payload = extract_json_object(openai_text_from_response(payload))
    raw_picks = model_payload.get("picks", [])
    if not isinstance(raw_picks, list):
        raise RuntimeError("OpenAI response did not include a picks array")

    fallback_by_id = {pick["id"]: pick for pick in picks}
    curated = []
    seen = set()
    for raw_pick in raw_picks:
        if not isinstance(raw_pick, dict):
            continue
        cleaned = clean_model_pick(raw_pick, fallback_by_id)
        if not cleaned or cleaned["id"] in seen:
            continue
        seen.add(cleaned["id"])
        curated.append(cleaned)

    if not curated:
        raise RuntimeError("OpenAI response did not return usable picks")
    return translate_source_titles_with_openai(curated[:limit], env)


def translate_source_titles_with_openai(picks: list[dict], env: dict[str, str]) -> list[dict]:
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return picks

    source_refs = []
    for pick_index, pick in enumerate(picks):
        for source_index, source in enumerate(pick.get("sources", [])):
            title = str(source.get("title", "")).strip()
            if title:
                source_refs.append(
                    {
                        "pickIndex": pick_index,
                        "sourceIndex": source_index,
                        "title": title,
                    }
                )

    if not source_refs:
        return picks

    model = env.get("OPENAI_AI_PICKS_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL
    body = {
        "model": model,
        "instructions": (
            "Return valid JSON only. For each supplied news headline, return a natural English headline. "
            "If it is already English, return it unchanged. Do not add facts or commentary."
        ),
        "input": json.dumps({"headlines": source_refs}, ensure_ascii=False),
        "max_output_tokens": 3000,
        "reasoning": {"effort": "minimal"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "headline_translations",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "headlines": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "pickIndex": {"type": "integer"},
                                    "sourceIndex": {"type": "integer"},
                                    "title": {"type": "string"},
                                },
                                "required": ["pickIndex", "sourceIndex", "title"],
                            },
                        }
                    },
                    "required": ["headlines"],
                },
            }
        },
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60, context=SSL_CONTEXT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        model_payload = extract_json_object(openai_text_from_response(payload))
    except Exception as error:
        print(f"warning: source-title translation failed: {error}", file=sys.stderr)
        return picks

    translated = model_payload.get("headlines", [])
    if not isinstance(translated, list):
        return picks

    updated = [dict(pick) for pick in picks]
    for pick in updated:
        pick["sources"] = [dict(source) for source in pick.get("sources", [])]

    for item in translated:
        if not isinstance(item, dict):
            continue
        try:
            pick_index = int(item.get("pickIndex"))
            source_index = int(item.get("sourceIndex"))
        except (TypeError, ValueError):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        if 0 <= pick_index < len(updated) and 0 <= source_index < len(updated[pick_index].get("sources", [])):
            updated[pick_index]["sources"][source_index]["title"] = title

    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate cached underlooked AI Picks for the globe.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum picks to write.")
    parser.add_argument("--per-query", type=int, default=3, help="Articles to inspect per watchlist query.")
    parser.add_argument("--discovery-per-query", type=int, default=8, help="Articles to inspect per broad discovery query.")
    parser.add_argument("--secondary-per-query", type=int, default=10, help="Articles to inspect per non-GDELT discovery source.")
    parser.add_argument("--rss-per-feed", type=int, default=12, help="Items to inspect per RSS feed.")
    parser.add_argument("--window-hours", type=int, default=48, help="GDELT lookback window.")
    parser.add_argument("--delay-seconds", type=float, default=6.0, help="Delay between GDELT queries.")
    parser.add_argument("--skip-openai", action="store_true", help="Use seeded/GDELT picks without OpenAI curation.")
    parser.add_argument("--skip-gdelt", action="store_true", help="Use seeded candidates without GDELT enrichment.")
    parser.add_argument("--skip-rss", action="store_true", help="Do not include RSS feed candidates.")
    parser.add_argument("--skip-discovery", action="store_true", help="Use only seeded watchlist candidates.")
    parser.add_argument("--preview-discovery", action="store_true", help="Print discovery candidates and quality diagnostics without writing output.")
    parser.add_argument("--preview-limit", type=int, default=25, help="Maximum discovery preview candidates to print.")
    return parser.parse_args()


def build_payload(args: argparse.Namespace | None = None) -> dict:
    if args is None:
        args = parse_args()
    env = load_env()
    provider = "underlooked-story-desk"
    discovery_picks = []

    if not args.skip_discovery:
        candidates = discover_candidates(args)
        if not args.skip_openai:
            try:
                discovered = curate_discovery_with_openai(candidates, args.limit, env)
            except Exception as error:
                print(f"warning: OpenAI discovery curation failed: {error}", file=sys.stderr)
                discovered = []
            if discovered:
                return {
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "provider": f"openai-discovery:{env.get('OPENAI_AI_PICKS_MODEL', DEFAULT_OPENAI_MODEL)}",
                    "windowHours": args.window_hours,
                    "selectionPrinciple": SELECTION_PRINCIPLE,
                    "picks": translate_source_titles_with_openai(discovered[: args.limit], env),
                }
        for candidate in candidates:
            pick = candidate_to_pick(candidate)
            if pick:
                discovery_picks.append(pick)
        discovery_picks = dedupe_picks(discovery_picks)
        discovery_picks.sort(key=lambda pick: (pick.get("importance", 0), pick.get("confidence", 0)), reverse=True)
        if len(discovery_picks) >= args.limit:
            return {
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "provider": "discovery-fallback",
                "windowHours": args.window_hours,
                "selectionPrinciple": SELECTION_PRINCIPLE,
                "picks": discovery_picks[: args.limit],
            }

    picks = []
    for index, config in enumerate(UNDERLOOKED_STORY_DESK):
        if index and not args.skip_gdelt:
            time.sleep(args.delay_seconds)
        articles = []
        if not args.skip_gdelt:
            try:
                articles = fetch_gdelt(config["query"], args.per_query, args.window_hours)
            except Exception as error:
                print(f"warning: {config['id']} query failed: {error}", file=sys.stderr)
        picks.append(build_pick(config, articles))

    picks.sort(key=lambda pick: pick["importance"], reverse=True)
    if discovery_picks:
        picks = dedupe_picks(discovery_picks + picks)
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "discovery-fallback+seeded",
            "windowHours": args.window_hours,
            "selectionPrinciple": SELECTION_PRINCIPLE,
            "picks": picks[: args.limit],
        }
    if not args.skip_openai:
        try:
            picks = curate_with_openai(picks, args.limit, env)
            provider = f"openai:{env.get('OPENAI_AI_PICKS_MODEL', DEFAULT_OPENAI_MODEL)}"
        except Exception as error:
            print(f"warning: OpenAI curation failed: {error}", file=sys.stderr)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "windowHours": args.window_hours,
        "selectionPrinciple": SELECTION_PRINCIPLE,
        "picks": picks[: args.limit],
    }


def main() -> int:
    args = parse_args()
    if args.preview_discovery:
        payload = preview_discovery(args)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    payload = build_payload(args)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(payload['picks'])} AI picks to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
