# Anakin's News Map

Map-first global news prototype.

## Mockup

- Open [index.html](./index.html) directly in a browser for the current mockup.

## Key Timing

- No API key is needed for the current prototype.
- I will need keys when we wire live article ingestion.
- First key to provide: your preferred news source API, unless you want me to start with GDELT only.

## Recommended Live Stack

- `GDELT`: country-aware story discovery and multilingual monitoring
- `The News API`: cleaner article metadata and source filtering
- `Wikidata`: government structure and officeholders
- `IFES ElectionGuide`: upcoming national elections
- `ACLED`: conflict indicator
- `LLM`: translation, clustering, summaries, and ranking

## Build Sequence

1. Replace sample country data with live fetchers.
2. Swap hotspot pins for a proper polygon world map.
3. Add caching and daily fact refresh.
4. Add article clustering and summary generation.

## Live Briefings

- Store your token in `.env.local` as `THE_NEWS_API_TOKEN=...`
- Start the app with `python3 scripts/serve_app.py`
- Open `http://127.0.0.1:4173/`
- A country refreshes only when clicked
- Once fetched, the result is cached for 24 hours in `data/cache/briefings.json`
- After 24 hours, the next click refreshes that country again

## Notes

- `The News API` is the scalable primary source in this first pass.
- `GDELT` is only used as a supplement when The News API comes back sparse.
- Click-triggered caching is the main API-usage control now.

## Country Facts

- Run `python3 scripts/fetch_country_facts.py`
- Generated facts land in `data/generated/country_facts.json`
- These facts load for every country at startup
- News still refreshes on click and stays cached for 24 hours

## Conflict Markers

- Run `python3 scripts/fetch_conflict_events.py`
- Generated marker data lands in `data/generated/conflict_events.json`
- Provider order: `ACLED`, then `UCDP GED`, then manual hotspot fallback
- Add `UCDP_API_TOKEN=...` to `.env.local` if you get a UCDP token
- As of April 28, 2026, UCDP documents token auth via the `x-ucdp-access-token` header
