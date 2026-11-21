# Flood Brief

A one-page, independent flood briefing for a volunteer planning or zoning board member.
Type in the address of a proposed development and get the flood risk today and under
projected sea-level rise, plus questions to ask the developer at the hearing.

## Mac setup

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

(Port 5000 is taken by AirPlay Receiver on macOS, so the app uses 5050.)

## Run it

```bash
pip install -r requirements.txt
python3 app.py            # live data -> http://localhost:5050
SAMPLE=1 python3 app.py   # built-in sample site, no internet needed
python3 -m pytest tests   # tests for the math
```

(On Windows PowerShell, use `$env:SAMPLE=1; python app.py`.)

## How it works

| Step | Source | File |
|---|---|---|
| Address -> coordinates + county | U.S. Census Geocoder | `sources.geocode` |
| Flood zone + base flood elevation (BFE) | FEMA National Flood Hazard Layer | `sources.fema_zone` |
| Ground elevation | USGS 3DEP point query | `sources.ground_elevation` |
| 100-year 24-hr rainfall | NOAA Atlas 14 | `sources.atlas14_24hr` |
| Flood-frequency curve | NOAA CO-OPS Extreme Water Levels (nearest NJ gauge) | `sources.gauge_curve` |
| Sea-level rise | Rutgers NJ STAP 2025 (0.9–1.7 ft by 2050, 2.2–3.8 ft by 2100 vs. 2005) | `config.py` |
| Future rainfall factors | NJDEP stormwater rule, by county | `config.py` |

**The core math (`risk.py`):**
1. FEMA's BFE has a 1% chance per year today. That is the anchor.
2. Sea-level rise of *s* ft makes that fixed height act like a height *s* ft lower on NOAA's
   gauge curve, so its yearly chance goes up. This is computed separately for each year.
3. P(at least one flood) = 1 − (1 − p₁)(1 − p₂)…(1 − pₙ).
4. A floor built *f* ft above the BFE sits *f* ft higher on the curve, so its odds drop.

No AI is used for numbers. Everything in the brief is computed in code.

## Before the hackathon (important)

1. **Test live mode on real addresses.** The data calls were written against the documented
   APIs and tested with mock responses, but not run against the live servers.
   Try 3–4 addresses and fix anything that breaks (FEMA is the most likely to be slow or picky).
2. **Pre-load your demo addresses:** run `python3 warm_cache.py` (and `python3 smoke_test.py`
   to check each data source on its own). Any lookup where geocode, FEMA and ground elevation
   succeed is saved to `cache/`, along with each tide gauge's curve. If the Wi-Fi fails during
   judging, or a live lookup comes back with more warnings, the app uses the saved copy.
3. Demo addresses (`config.DEMO_ADDRESSES`, also the "Try:" buttons): Sea Bright and Keansburg
   (coastal AE zones) and Manville (inland, outside the FEMA floodplain, flooded by Ida in 2021).

## Suggested team split

- **Data:** get live mode working on real addresses; pre-cache demo sites.
- **Math/content:** own `risk.py` + `brief.py`; be ready to explain the formula and caveats to judges.
- **Front end:** polish `static/index.html`; make sure Print -> PDF fits on one or two pages.
- **Pitch:** 2-minute story (board member, hearing Tuesday, developer has a 200-page report).

## Known limits (say these before a judge does)

- Planning estimates, not engineering certifications.
- Sea-level adjustment only applies to coastal sites (FEMA coastal/V zones, or low-lying sites
  near a gauge). Inland sites get today's odds plus the rainfall projection.
- Odds for floors above the BFE extend the gauge curve past its 1% end point (an estimate).
- The NJDEP rainfall factors are for 2050–2099, upper likely range, moderate emissions.
- "Central" sea-level rise is the midpoint of the STAP likely range; the report gives no median.

## Stretch ideas

- Map of the parcel with today's flood zone and a 2050 water line
- Pull a board meeting agenda and generate briefs for every listed project
- "Resident" mode that turns the brief into a public comment draft
