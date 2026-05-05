#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path

import fetch_ai_picks


ROOT = Path(__file__).resolve().parents[1]
CONFLICT_PATH = ROOT / "data" / "generated" / "conflict_events.json"
CARRIER_PATH = ROOT / "data" / "generated" / "us_carriers.json"

CONFLICT_CONTEXT = {
    "ukr-donetsk": "Russia's war against Ukraine has been full-scale since February 2022, with military pressure around Donetsk and the wider Donbas tracing back to 2014. The eastern front remains heavily attritional, with neither side making large territorial gains quickly; the live angle is whether drone, artillery, and manpower pressure can turn localized advances into something operationally significant.",
    "ukr-zaporizhzhia": "Southern Ukraine remains a static but strategically important front because it points toward the land corridor to Crimea. The recent issue is less sweeping maneuver than whether strikes, fortifications, and logistics pressure change the balance around Zaporizhzhia and the lower Dnipro.",
    "gaza-strip": "Gaza remains the densest urban-war marker on the map. The conflict is tied to the wider Iran-Israel regional confrontation, but the local story is civilian movement, aid access, hostage and ceasefire diplomacy, and whether Israeli operations shift from raids to a more durable political arrangement.",
    "south-lebanon": "South Lebanon is the pressure gauge for a wider Israel-Hezbollah confrontation. The front is not a conventional invasion line every day; it is a cycle of strikes, evacuations, rocket fire, and deterrence signaling that can widen if either side misreads the other.",
    "red-sea-yemen": "The Red Sea/Yemen marker tracks Houthi missile and drone pressure on shipping and the military responses around Bab el-Mandeb. The recent question is whether attacks and insurance costs keep commercial vessels away from Suez even when headline attention moves elsewhere.",
    "khartoum": "Sudan's war between the army and the RSF has turned Khartoum into a fragmented urban battlefield and governance crisis. The current signal is whether control shifts in the capital translate into aid access or simply move fighting and displacement elsewhere.",
    "darfur": "Darfur is the most worrying Sudan spillover marker because local violence, displacement, ethnic targeting risk, and cross-border routes into Chad all overlap. The live angle is whether pressure around El Fasher and nearby corridors worsens the humanitarian emergency.",
    "sahel-tri-border": "The Sahel tri-border zone is a long-running insurgency belt across Mali, Burkina Faso, and Niger. Recent coordinated attacks in Mali make this more than a background-security problem because junta legitimacy, Russian support, and cross-border militant mobility are all in play.",
    "lake-chad": "Lake Chad remains a regional insurgency system rather than a single-country conflict. Boko Haram and Islamic State-linked violence affects Nigeria, Niger, Cameroon, and Chad through raids, displacement, and hard-to-secure islands and border communities.",
    "cameroon-far-north": "Far North Cameroon is tied into the Lake Chad insurgency ecosystem. It is often undercovered because events are smaller than the main Nigeria headlines, but the strategic issue is border insecurity and civilian vulnerability in a region with limited state reach.",
    "myanmar-sagaing": "Sagaing is one of the core resistance-war zones in Myanmar's post-coup civil war. The live issue is whether anti-junta forces can hold territory and disrupt military logistics while civilians face airstrikes, displacement, and fragmented governance.",
    "drc-kivu": "Eastern DRC and Kivu remain shaped by M23, Congolese forces, regional involvement, and civilian displacement. The recent angle is whether diplomacy and ceasefire language mean anything on the ground when armed groups still control roads and mining areas.",
    "kashmir-line": "Kashmir is a militarized India-Pakistan flashpoint where local attacks, arrests, or border fire can quickly become crisis diplomacy between nuclear-armed states. The live signal is whether any incident changes troop posture or air and border restrictions.",
}

CARRIER_CONTEXT = {
    "ford-red-sea": {
        "area": "Eastern Mediterranean Sea",
        "status": "Operating in the Eastern Mediterranean Sea",
        "lat": 34.7,
        "lon": 28.4,
        "context": "USS Gerald R. Ford is the lead ship of the newest U.S. carrier class and one of the most advanced carriers in service. USNI's May 4 tracker places the Ford Carrier Strike Group in the Eastern Mediterranean, with destroyers also present in nearby theaters; the live significance is that Ford provides airpower, command capacity, and deterrence close to the Middle East without being listed as in the Red Sea itself.",
    },
    "lincoln-arabian-sea": {
        "area": "Arabian Sea",
        "status": "Operating in the Arabian Sea in support of Operation Epic Fury",
        "lat": 17.1,
        "lon": 64.8,
        "context": "USS Abraham Lincoln is a Nimitz-class carrier operating in the Arabian Sea. The current significance is its role in U.S. 5th Fleet maritime security and strike capacity near the Gulf while regional tension around Iran and shipping remains elevated.",
    },
    "bush-arabian-sea": {
        "area": "Arabian Sea",
        "status": "Operating in the Arabian Sea after joining the U.S. 5th Fleet buildup",
        "lat": 14.0,
        "lon": 66.2,
        "context": "USS George H.W. Bush is also in the Arabian Sea, giving the U.S. an unusually heavy carrier presence near the Gulf. Its live significance is reinforcement: another flight deck, escorts, and command capacity in a theater where oil routes and Iran pressure matter.",
    },
    "george-washington-yokosuka": {
        "area": "Yokosuka, Japan",
        "status": "In port in Yokosuka, Japan",
        "lat": 35.283,
        "lon": 139.667,
        "context": "USS George Washington is the forward-deployed U.S. carrier based in Japan. Even in port, it matters because it anchors U.S. naval presence in the Western Pacific near Taiwan, the Korean Peninsula, and the East China Sea.",
    },
    "theodore-roosevelt-east-pac": {
        "area": "Eastern Pacific",
        "status": "Operating in the Eastern Pacific",
        "lat": 27.0,
        "lon": -126.0,
        "context": "USS Theodore Roosevelt is operating in the Eastern Pacific. The current meaning is readiness and presence closer to the U.S. West Coast and Pacific approaches rather than direct involvement in Middle East operations.",
    },
    "nimitz-magellan": {
        "area": "South Atlantic off Argentina",
        "status": "Operating off Argentina during Southern Seas 2026 while transiting toward Virginia",
        "lat": -45.0,
        "lon": -58.0,
        "context": "USS Nimitz is the oldest active U.S. carrier and is circumnavigating South America toward Virginia before eventual decommissioning. USNI places it off Argentina for Southern Seas 2026, making this more of a diplomacy, exercise, and end-of-service transit story than a combat deployment.",
    },
}


def summarize_with_openai(items: list[dict], item_type: str) -> dict[str, dict]:
    env = fetch_ai_picks.load_env()
    model = env.get("OPENAI_AI_PICKS_MODEL", fetch_ai_picks.DEFAULT_OPENAI_MODEL)
    if not env.get("OPENAI_API_KEY"):
        return {}

    prompt = {
        "task": f"Write concise marker briefings for Pumpkin News {item_type}.",
        "rules": [
            "Use only the supplied context. Do not invent locations, missions, casualty counts, or breaking news.",
            "Write in a calm news-briefing voice.",
            "Each summary should be 55-85 words.",
            "Each recentDevelopment should be one specific sentence based on the supplied context.",
            "Return one briefing object per supplied id.",
        ],
        "items": items,
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "briefings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "recentDevelopment": {"type": "string"},
                    },
                    "required": ["id", "title", "summary", "recentDevelopment"],
                },
            }
        },
        "required": ["briefings"],
    }
    body = {
        "model": model,
        "instructions": "You write compact geopolitical map marker briefings. Return valid JSON only.",
        "input": json.dumps(prompt, ensure_ascii=False),
        "max_output_tokens": 6000,
        "reasoning": {"effort": "minimal"},
        "text": {"format": {"type": "json_schema", "name": "marker_briefings", "strict": True, "schema": schema}},
    }
    request = fetch_ai_picks.urllib.request.Request(
        fetch_ai_picks.OPENAI_RESPONSES_ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {env['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with fetch_ai_picks.urllib.request.urlopen(request, timeout=60, context=fetch_ai_picks.SSL_CONTEXT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    parsed = fetch_ai_picks.extract_json_object(fetch_ai_picks.openai_text_from_response(payload))
    return {
        str(item.get("id")): item
        for item in parsed.get("briefings", [])
        if isinstance(item, dict) and item.get("id")
    }


def fallback_briefing(title: str, context: str) -> dict:
    return {
        "title": title,
        "summary": context,
        "recentDevelopment": context.split(". ")[-1].rstrip(".") + ".",
    }


def enrich_conflicts() -> None:
    payload = json.loads(CONFLICT_PATH.read_text())
    items = [
        {
            "id": hotspot["id"],
            "label": hotspot["label"],
            "conflict": hotspot["conflict"],
            "kind": hotspot["kind"],
            "countries": hotspot.get("countries", []),
            "context": CONFLICT_CONTEXT.get(hotspot["id"], ""),
        }
        for hotspot in payload.get("hotspots", [])
    ]
    generated = summarize_with_openai(items, "live conflicts")
    for hotspot in payload.get("hotspots", []):
        context = CONFLICT_CONTEXT.get(hotspot["id"], f"{hotspot['label']} is part of {hotspot['conflict']}.")
        brief = generated.get(hotspot["id"]) or fallback_briefing(hotspot["label"], context)
        hotspot["briefing"] = {
            "label": hotspot["label"],
            "kind": hotspot["conflict"],
            "marketCard": hotspot.get("marketCard"),
            "stories": [
                {
                    "source": "GPT-5 nano",
                    "time": "Current context",
                    "title": brief.get("title") or hotspot["label"],
                    "summary": brief.get("summary") or context,
                    "tags": [hotspot.get("kind"), hotspot.get("conflict"), "Live conflict"],
                    "url": hotspot.get("sourceUrl", ""),
                },
                {
                    "source": "Recent development",
                    "time": "Now",
                    "title": "What to watch",
                    "summary": brief.get("recentDevelopment") or context,
                    "tags": ["Signal", "Map note"],
                    "url": hotspot.get("sourceUrl", ""),
                },
            ],
        }
    CONFLICT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def enrich_carriers() -> None:
    payload = json.loads(CARRIER_PATH.read_text())
    payload["generatedAt"] = "2026-05-04T12:53:00Z"
    payload["source"] = "USNI Fleet and Marine Tracker"
    payload["sourceUrl"] = "https://news.usni.org/2026/05/04/usni-news-fleet-and-marine-tracker-may-4-2026"
    payload["asOf"] = "2026-05-04"
    for carrier in payload.get("carriers", []):
        current = CARRIER_CONTEXT.get(carrier["id"])
        if current:
            carrier.update({key: current[key] for key in ["area", "status", "lat", "lon"]})
    items = [
        {
            "id": carrier["id"],
            "name": carrier["name"],
            "hull": carrier["hull"],
            "area": carrier["area"],
            "status": carrier["status"],
            "context": CARRIER_CONTEXT.get(carrier["id"], {}).get("context", ""),
        }
        for carrier in payload.get("carriers", [])
    ]
    generated = summarize_with_openai(items, "US carrier positions")
    for carrier in payload.get("carriers", []):
        context = CARRIER_CONTEXT.get(carrier["id"], {}).get("context", carrier["status"])
        brief = generated.get(carrier["id"]) or fallback_briefing(carrier["name"], context)
        carrier["sourceUrl"] = payload["sourceUrl"]
        carrier["briefing"] = {
            "label": carrier["name"],
            "kind": f"{carrier['hull']} · {carrier['area']}",
            "stories": [
                {
                    "source": "USNI + GPT-5 nano",
                    "time": payload["asOf"],
                    "title": brief.get("title") or carrier["name"],
                    "summary": brief.get("summary") or context,
                    "tags": [carrier["hull"], carrier["area"], "Carrier"],
                    "url": payload["sourceUrl"],
                },
                {
                    "source": "Recent development",
                    "time": "Now",
                    "title": "What to watch",
                    "summary": brief.get("recentDevelopment") or carrier["status"],
                    "tags": ["Naval posture", "Map note"],
                    "url": payload["sourceUrl"],
                },
            ],
        }
    CARRIER_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main() -> int:
    enrich_conflicts()
    enrich_carriers()
    print("Enriched conflict and carrier marker briefings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
