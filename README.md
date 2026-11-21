# Flood Brief

**A one-page flood briefing for the volunteers who approve buildings on the Jersey Shore.**

Type in the address of a proposed development. In seconds, Flood Brief produces a printable
brief showing the site's flood risk today, how that risk grows as the sea rises, and the
questions a board member should ask the developer at the hearing.

---

## The problem

In New Jersey, local planning and zoning boards decide whether new buildings in flood zones
get approved. Most board members are unpaid volunteers, not engineers. The developer arrives
with paid consultants and a thick technical report; the board member usually has nothing
independent to check it against.

The main public reference, FEMA's flood map, is based on past floods. It does not include
projected sea-level rise. But a building approved today will still be standing in 2075, facing
a higher ocean. So towns make 50-year decisions with a picture of risk that is already out of
date.

## Who it's for

A volunteer zoning or planning board member who has a hearing coming up and needs a clear,
independent read on one site's flood risk, in plain language, on one page.

## What the brief shows

| Section | What the board member learns |
|---|---|
| **Bottom line** | The chance of at least one major flood over a 30-year mortgage, on today's map and with sea-level rise |
| **Today** | FEMA flood zone, base flood elevation, ground elevation, and how far below the flood level the site sits |
| **Future odds** | Low, central and high sea-level-rise scenarios, side by side |
| **Raising the floor** | How much safer the building gets if its lowest floor is built 1, 2 or 3 feet higher |
| **Heavy rain** | Today's 100-year rainstorm and how much heavier it is projected to get in that county |
| **Questions to ask** | Specific questions for the developer, generated from the site's data |

### Example: a coastal site near Sandy Hook

| Situation | Chance of at least one major flood in 30 years |
|---|---|
| Today's FEMA map | 26% |
| With projected sea-level rise (central) | 35% |
| Lowest floor built 2 ft higher | 8% |

The last row is the point: it turns a worrying number into a decision the board can act on.

---

## How it works

### 1. Data (all public)

| What | Source |
|---|---|
| Address to map coordinates and county | U.S. Census Geocoder |
| Flood zone and base flood elevation | FEMA National Flood Hazard Layer |
| Ground elevation | USGS 3D Elevation Program |
| 100-year, 24-hour rainfall | NOAA Atlas 14 |
| How often each water level occurs at the coast | NOAA tide gauges (nearest NJ station) |
| Sea-level-rise projections | Rutgers NJ Science & Technical Advisory Panel, 2025 (0.9–1.7 ft by 2050; 2.2–3.8 ft by 2100, vs. 2005) |
| Future rainfall increase by county | NJDEP stormwater rules |

### 2. The math

1. **Start with FEMA's definition.** The base flood elevation is the water level with a 1% chance
   of being reached in any year.
2. **Add sea-level rise.** As the sea rises, that same water level is reached more easily. Using
   NOAA's tide-gauge records, the tool works out each future year's chance separately.
3. **Combine the years.** The chance of at least one flood over the period is
   **1 − (1 − p₁)(1 − p₂)…(1 − pₙ)**, where each p is one year's chance.
4. **Test higher floors.** A floor built higher sits further up the same curve, so its chance of
   flooding drops.

All of this is in `risk.py` and `brief.py`, with automated tests for the math in `tests/`.

### 3. Every number is labeled

So a reader always knows how much to trust a number, each one in the brief carries a marker,
explained in a legend at the top of the page:

| Marker | Label | Meaning | Examples |
|---|---|---|---|
| Green circle | **Measured** | Taken directly from FEMA, USGS or NOAA data | ground elevation, base flood elevation, today's 100-year rainfall |
| Charcoal triangle | **Modeled** | Calculated by Flood Brief | every flood chance (26%, 35%), "1 in 53 per year", future rainfall |
| Orange diamond | **Assumed** | A chosen time span, scenario, floor height or standard definition | the 30-year span, sea-level-rise scenarios, "100-year flood = 1% per year" |

---

## How we incorporated Gemini 3.8 Flash

**AI never calculates anything.** Every number is computed in code from public data.

AI (Google Gemini) is used for one optional job: writing a three-sentence plain-language summary
of the finished brief, with an optional Spanish translation for residents and board members who
prefer it. Claude Code (Opus 5.5) was also incorporated in some areas within the production of this website.

Because a wrong number in a public hearing would undermine the whole tool, the summary passes a
strict check before anyone sees it:

- **Number check.** Every number in the AI's summary must match a number in the brief. If even one
  doesn't, the summary is thrown out and the page shows "Summary unavailable."
- **Labels must match.** The summary must keep each number's Measured / Modeled / Assumed label.
- **Verified badge.** Summaries that pass are marked "numbers verified."
- **Works without AI.** If the AI is unavailable, the brief is complete on its own. On the public
  demo site, AI summaries are pre-generated and verified for the demo addresses only.

Known limit of the check: very small numbers (like 1, 2, 3) appear throughout the brief, so they
always pass, and numbers written as words aren't checked (the AI is instructed to use digits).

---

## Limitations

We want to be clear about what this tool is and isn't.

- **Planning estimates, not engineering certifications.** The brief helps a board ask better
  questions. It doesn't replace a licensed engineer.
- **Sea-level rise applies to coastal sites only.** Inland sites get today's flood odds plus the
  rainfall projection.
- **Floors above the flood level are an estimate.** NOAA's records stop at the 1%-per-year level,
  so odds for higher floors extend the curve past its last data point.
- **Rainfall factors are long-range.** NJDEP's factors cover 2050–2099 under moderate emissions.
- **"Central" sea-level rise is our choice.** It's the midpoint of the Rutgers likely range, which
  gives no single best estimate.

---

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 app.py            # live data at http://localhost:5050
SAMPLE=1 python3 app.py   # sample site, no internet needed
python3 -m pytest tests   # run the math tests
```

To enable AI summaries locally, put `GEMINI_API_KEY=...` in a `.env` file in this folder.

## What's next

- A map of the parcel showing today's flood zone and a 2050 water line
- Briefs for every project on an upcoming board meeting agenda
- A resident version that helps people write a public comment
