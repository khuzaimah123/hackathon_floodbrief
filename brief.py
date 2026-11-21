"""
Turns raw data into the brief: numbers, a headline, and questions for the developer.
Every number in the output is computed here in code (no AI guesses).
"""
import datetime

import config
import risk
import sources


def pct(x):
    return f"{round(100 * x)}%"


def one_in(p):
    return f"1 in {round(1 / p)}" if p > 0 else "—"


def fetch_site(address):
    """Call every data source. Geocoding is required; the rest degrade gracefully."""
    warnings = []
    site = sources.geocode(address)
    lat, lon = site["lat"], site["lon"]

    def attempt(label, fn, *args):
        try:
            return fn(*args)
        except sources.SourceError as e:
            warnings.append(f"{label} unavailable: {e}")
            return None

    site["fema"] = attempt("FEMA flood zone", sources.fema_zone, lat, lon)
    site["ground_ft"] = attempt("Ground elevation", sources.ground_elevation, lat, lon)
    site["rain_depths"] = attempt("NOAA rainfall", sources.atlas14_24hr, lat, lon)

    sid, gauge, miles = sources.nearest_gauge(lat, lon)
    site["gauge"] = {"id": sid, "name": gauge["name"], "miles": round(miles, 1)}
    curve = attempt("NOAA gauge curve", sources.gauge_curve, sid)
    if curve is None and sid == "8531680":
        curve = config.SANDY_HOOK_CURVE
        warnings.append("Using saved Sandy Hook curve.")
    site["gauge"]["curve"] = curve
    site["warnings"] = warnings
    return site


def is_coastal(site):
    f = site.get("fema") or {}
    zone, sub = (f.get("zone") or ""), (f.get("subtype") or "").upper()
    if zone.startswith("V") or "COASTAL" in sub:
        return True
    g, ground = site.get("gauge") or {}, site.get("ground_ft")
    return (g.get("miles", 999) <= config.COASTAL_MAX_MILES and ground is not None
            and ground <= config.COASTAL_MAX_GROUND_FT)


def build_brief(site, years=30, freeboard_ft=0.0, start_year=None):
    start_year = start_year or datetime.date.today().year
    end_year = start_year + years - 1
    fema = site.get("fema") or {}
    in_sfha = bool(fema.get("in_sfha"))
    coastal = is_coastal(site)
    curve = (site.get("gauge") or {}).get("curve")
    ground, bfe = site.get("ground_ft"), fema.get("bfe_ft")

    out = {
        "site": {k: site[k] for k in ("matched_address", "lat", "lon", "county")},
        "years": years, "start_year": start_year, "end_year": end_year,
        "freeboard_ft": freeboard_ft,
        "today": {
            "zone": fema.get("zone"), "subtype": fema.get("subtype"), "in_sfha": in_sfha,
            "bfe_ft": bfe, "bfe_datum": fema.get("datum"),
            "ground_ft": round(ground, 1) if ground is not None else None,
            "ground_below_bfe_ft": round(bfe - ground, 1) if (bfe is not None and ground is not None) else None,
        },
        "coastal": coastal,
        "gauge": {k: v for k, v in (site.get("gauge") or {}).items() if k != "curve"},
        "odds": None, "rain": None, "headline": [], "questions": [],
        "warnings": list(site.get("warnings", [])),
        "sample": bool(site.get("sample")),
    }

    # ---- Flood odds -------------------------------------------------------
    if in_sfha:
        p_today = 0.01
        if coastal and curve and freeboard_ft:
            anchor = risk.level_at_prob(curve, 0.01)
            p_today = risk.prob_at_level(curve, anchor + freeboard_ft)
        today = risk.fixed_chance(p_today, years)
        odds = {"today_map": today, "p_today": p_today, "scenarios": {}, "freeboard": []}
        if coastal and curve:
            for name, scen in config.SLR_SCENARIOS.items():
                ps = risk.coastal_annual_probs(curve, start_year, years, scen, freeboard_ft)
                odds["scenarios"][name] = {
                    "chance": risk.chance_of_at_least_one(ps),
                    "p_end": ps[-1], "p_start": ps[0],
                }
            central = config.SLR_SCENARIOS["central"]
            for fb in (0, 1, 2, 3):
                ps = risk.coastal_annual_probs(curve, start_year, years, central, fb)
                odds["freeboard"].append({"feet": fb, "chance": risk.chance_of_at_least_one(ps)})
        out["odds"] = odds

        if odds["scenarios"]:
            c = odds["scenarios"]["central"]
            lo, hi = odds["scenarios"]["low"]["chance"], odds["scenarios"]["high"]["chance"]
            floor_note = "" if freeboard_ft == 0 else f" for a floor {freeboard_ft:g} ft above the base flood elevation"
            out["headline"].append(
                f"Over {years} years, the chance of at least one major flood{floor_note} is about "
                f"{pct(today)} on today's FEMA map, and about {pct(c['chance'])} "
                f"(range {pct(lo)}–{pct(hi)}) once projected sea-level rise is included.")
            what = ("today's 100-year flood level" if not freeboard_ft
                    else f"a floor {freeboard_ft:g} ft above the base flood elevation")
            out["headline"].append(
                f"By {end_year}, {what} floods about as often as a "
                f"{round(1 / c['p_end'])}-year flood does today (central projection).")
            fb2 = next(x for x in odds["freeboard"] if x["feet"] == 2)
            fb0 = odds["freeboard"][0]
            out["headline"].append(
                f"Raising the lowest floor 2 ft above the base flood elevation cuts the "
                f"{years}-year odds from {pct(fb0['chance'])} to {pct(fb2['chance'])}.")
        else:
            out["headline"].append(
                f"Over {years} years, the chance of at least one major flood is about "
                f"{pct(today)} on today's FEMA map (about 1 in {round(1 / today)}).")
    else:
        zone = fema.get("zone") or "unmapped"
        out["headline"].append(
            f"This site is outside FEMA's 1% annual-chance floodplain (zone {zone}). "
            "That means lower, not zero, risk: heavy rainfall floods areas the maps miss.")

    # ---- Rainfall -------------------------------------------------------------
    depths, county = site.get("rain_depths"), site.get("county")
    if depths:  # JSON (cache/sample) turns int keys into strings
        depths = {int(k): float(v) for k, v in depths.items()}
    factors = config.RAIN_CHANGE_FACTORS.get(county or "")
    if depths and 100 in depths:
        rain = {"today_100yr_in": depths[100], "county": county}
        if factors:
            d_today, d_future, T_new = risk.future_return_period(depths, factors)
            rain.update({"future_100yr_in": round(d_future, 1),
                         "pct_increase": round(100 * (factors[100] - 1)),
                         "today_storm_future_return_period": round(T_new) if T_new else None})
            if T_new:
                out["headline"].append(
                    f"Rain: today's 100-year, 24-hour storm ({d_today:.1f} in) is projected to "
                    f"become roughly a {round(T_new)}-year storm later this century "
                    f"(NJDEP design factor for {county} County).")
        out["rain"] = rain

    out["questions"] = questions(out)
    return out


def questions(b):
    q, t, odds = [], b["today"], b.get("odds") or {}
    if t["in_sfha"]:
        bfe = f" ({t['bfe_ft']:g} ft)" if t["bfe_ft"] is not None else ""
        q.append(f"How high is the lowest floor above the base flood elevation{bfe}, and does it "
                 "meet state and local freeboard requirements?")
    if odds.get("freeboard"):
        fb = {x["feet"]: x["chance"] for x in odds["freeboard"]}
        q.append(f"Was the design based on today's flood map or projected sea level? "
                 f"At the base flood elevation the {b['years']}-year odds are about {pct(fb[0])}; "
                 f"2 ft higher they drop to about {pct(fb[2])}. What would the extra elevation cost?")
    if t["ground_below_bfe_ft"] is not None and t["ground_below_bfe_ft"] > 0:
        q.append(f"The ground sits about {t['ground_below_bfe_ft']:g} ft below the base flood "
                 "elevation. Will the site be filled, and where does displaced water go?")
    if (t["zone"] or "").startswith("V"):
        q.append("This is a wave-hazard (V) zone. Is the building on an open foundation "
                 "designed for wave forces?")
    rain = b.get("rain") or {}
    if rain.get("pct_increase") is not None:
        q.append(f"Is the stormwater system sized with NJDEP's future-rainfall factors "
                 f"(100-year storm +{rain['pct_increase']}% in {rain['county']} County)?")
    q.append("Are electrical, HVAC and other mechanical systems above flood level?")
    q.append("During a flood, can residents and emergency vehicles still reach the site? "
             "How high is the access road?")
    if not t["in_sfha"]:
        q.insert(0, "The site is outside the mapped floodplain. How does the design handle a "
                    "rainfall event like Tropical Storm Ida (2021)?")
    return q
