# Flood Brief: fix list (work through in order)

Context: this is a Flask app for a hackathon, and the demo is at 5:30 PM today. Keep every change small and safe.
Rule that overrides everything: **never invent numbers.** Every figure must come from an API response
or a constant in `config.py` with a source comment. Run `python -m pytest tests` after each section.
Commit with git after each section (run `git init` first if this isn't a repo yet) so we can roll back.

Already verified (don't change):
- `SANDY_HOOK_CURVE` matches NOAA's live API exactly.
- The `GEV_HI.exceedanceLevels` JSON shape is correct.
- The Atlas 14 URL returns a single "24-hr" row.
- The STAP numbers (0.9–1.7 ft by 2050, 2.2–3.8 ft by 2100) match the 2025 Rutgers report.

---

## Section 1: make it run on this Mac (do first)

1. macOS uses port 5000 for AirPlay Receiver, so `python app.py` will collide. Change the default port in
   `app.py` to 5050 and update the docstring and README to say http://localhost:5050.
2. Set up a virtual environment and install:
   `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
   Add a "Mac setup" block to the README with exactly these commands (use `python3`, not `python`).
3. Add a `.gitignore` with: `.venv/`, `__pycache__/`, `.env`, `.pytest_cache/`. Do **not** ignore `cache/`.
   We want the demo addresses committed.

## Section 2: live smoke test (show me the output before going on)

4. Create `smoke_test.py`. It runs each source in `sources.py` separately for
   "100 Ocean Ave, Long Branch, NJ 07740" and prints OK/FAIL, the time taken, and the key values for each.
   - First, fetch `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28?f=json` and print
     the layer name and field names, to confirm layer 28 is the Flood Hazard Zones layer with
     FLD_ZONE / ZONE_SUBTY / SFHA_TF / STATIC_BFE / V_DATUM.
   - If it isn't, find the right layer ID from `MapServer?f=json` and fix `config.FEMA_NFHL_ZONES`.
   - Run it, show me the output, and fix any source that fails. Then also run it for a Sea Bright and a
     Keansburg address.
5. In `sources.fema_zone`, if `V_DATUM` is anything other than NAVD88 (for example NGVD29), have
   `brief.fetch_site` add a warning:
   "Flood map uses {datum}; the ground-vs-flood-level comparison may be off by about 1 ft."

## Section 3: demo reliability (most important)

6. **Caching bug:** `load_site` only caches when there are zero warnings, so if any optional source
   (rainfall, gauge) times out, nothing is ever cached and offline mode can't work. Change it to:
   - Save the lookup to the cache whenever geocode, FEMA, and ground elevation all succeeded,
     even if there are warnings. Store a count of the warnings.
   - When the live lookup fails **or** returns more warnings than the cached copy, use the cached copy
     and add the warning "Using data saved {saved_at}."
   - Normalize the cache key: lowercase, strip punctuation, and collapse whitespace.
7. Gauge curve fallback: when a live `gauge_curve` call succeeds, save it to `cache/curve_{station}.json`.
   When the live call fails, load that file if it exists, and only fall back to `config.SANDY_HOOK_CURVE`
   after that. This covers Atlantic City, Cape May, and The Battery too.
8. Create `warm_cache.py`. It runs full live lookups for our 3 demo addresses (listed in a `DEMO_ADDRESSES`
   list in `config.py`) and prints a status table. We'll run it before judging.
9. In `static/index.html`, add 3 small "Try:" buttons under the form that fill in the demo addresses and
   submit. That way the address string always matches the cache.

## Section 4: correctness and wording

10. Headline 3 and question 2 always compare "at BFE" vs "2 ft above" even when the user already set a
    floor height. Make both compare the user's chosen floor `f` to `f + 2` ft. Extend the freeboard table to
    cover `f, f+1, f+2, f+3`, and keep the existing 0 ft row when `f > 0`.
11. `pct()` shows "0%" for small values. Return "<1%" when 0 < x < 0.005. Do the same in the JS `pct`.
12. Grammar: "Over 1 years" → use "year" when years == 1.
13. The floor-height input only affects coastal sites. When `freeboard_ft > 0` and the site is not coastal
    (or has no gauge curve), add a warning "Floor height only changes the odds for coastal sites."
    Hide the "floor X ft above BFE" text in the page meta line in that case.
14. `risk.level_at_prob` raises ValueError if a live curve doesn't include 0.01. Make `build_brief` catch
    that and fall back to today-map-only odds with a warning, instead of crashing with a 500 error.
15. In `sample_site.json`, replace `rain_depths` with the real NOAA Atlas 14 values at the sample
    coordinates (40.30, −73.98), which are 1:2.88, 2:3.50, 5:4.52, 10:5.40, 25:6.73, 50:7.90, 100:9.21,
    200:10.7, 500:12.9, 1000:14.9. Update the test in `tests/test_risk.py` that uses the old depths only if
    it depends on `sample_site.json` (it currently has its own hard-coded depths, so leave it).

## Section 5: Gemini side quest (only after Sections 1–4 pass)

16. Add an optional "Plain-English summary" and a "Translate (Spanish)" button.
    - Backend route `/api/summary` takes the brief JSON and calls Gemini with the `google-genai` Python
      SDK (add it to requirements). Use the current Gemini Flash model and read `GEMINI_API_KEY` from
      the environment.
    - Prompt: write a 3-sentence summary for a volunteer zoning board member, using only numbers that
      appear in the provided JSON.
    - **Guardrail:** extract every number from the model output with a regex and check that each one
      appears in the input JSON (after rounding). If any doesn't, discard the output and return
      "Summary unavailable." Show a small "numbers verified" badge when it passes.
    - If no API key is set, hide the buttons.

## Section 6: tests

17. Add tests for:
    - Partial lookups getting cached (mock `brief.fetch_site` to return a warning).
    - `pct(0.002) == "<1%"`.
    - The headline comparing `f` vs `f + 2` when freeboard = 2.
    - Graceful fallback when the curve lacks 0.01.
    - The Gemini number guardrail rejecting an invented number.
18. Run all tests. Then run `SAMPLE=1 python3 app.py` and confirm the page renders.

When done, give me a short summary of what changed and anything that still fails live.
