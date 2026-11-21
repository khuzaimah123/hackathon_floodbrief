"""Tests for caching, brief wording/fallbacks and the Gemini number guardrail (no network)."""
import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app  # noqa: E402
import brief  # noqa: E402
import config  # noqa: E402
import sources  # noqa: E402
import summary  # noqa: E402

ADDRESS = "1167 Ocean Ave, Sea Bright, NJ 07760"


@pytest.fixture
def sample_site():
    with open(os.path.join(ROOT, "sample_site.json")) as f:
        site = json.load(f)
    site["warnings"] = []
    return site


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    """Point every cache at a temp dir so tests never touch the real cache/."""
    monkeypatch.setattr(app, "CACHE", str(tmp_path))
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SAMPLE", raising=False)
    return tmp_path


def fake_site(warnings, fema=True, ground=True):
    return {"lat": 40.35, "lon": -73.97, "matched_address": "X", "county": "Monmouth",
            "fema": {"zone": "AE", "in_sfha": True, "bfe_ft": 9.0} if fema else None,
            "ground_ft": 5.0 if ground else None, "rain_depths": None,
            "gauge": {"id": "8531680", "name": "Sandy Hook, NJ", "miles": 8.3, "curve": None},
            "warnings": list(warnings)}


# ---------------------------------------------------------------------------
# Caching (app.load_site)
# ---------------------------------------------------------------------------
def test_partial_lookup_is_cached(cache_dir, monkeypatch):
    monkeypatch.setattr(brief, "fetch_site",
                        lambda a, **kw: fake_site(["NOAA rainfall unavailable: timeout"]))
    site = app.load_site(ADDRESS)
    assert site["warnings"] == ["NOAA rainfall unavailable: timeout"]
    saved = app.read_json(app.cache_path(ADDRESS))
    assert saved is not None and saved["warning_count"] == 1


def test_lookup_missing_fema_is_not_cached(cache_dir, monkeypatch):
    monkeypatch.setattr(brief, "fetch_site", lambda a, **kw: fake_site(["FEMA down"], fema=False))
    app.load_site(ADDRESS)
    assert not os.path.exists(app.cache_path(ADDRESS))


def test_cached_copy_used_when_live_fails_or_is_worse(cache_dir, monkeypatch):
    monkeypatch.setattr(brief, "fetch_site", lambda a, **kw: fake_site([]))
    app.load_site(ADDRESS)  # clean lookup saved

    def down(a, **kw):
        raise sources.SourceError("no internet")
    monkeypatch.setattr(brief, "fetch_site", down)
    site = app.load_site(ADDRESS)
    assert site["warnings"][-1].startswith("Using data saved ")

    monkeypatch.setattr(brief, "fetch_site", lambda a, **kw: fake_site(["NOAA gauge curve unavailable"]))
    site = app.load_site(ADDRESS)
    assert site["warnings"][-1].startswith("Using data saved ")


def test_quick_usgs_only_when_saved_copy_exists(cache_dir, monkeypatch):
    calls = []
    monkeypatch.setattr(brief, "fetch_site", lambda a, quick=False: calls.append(quick) or fake_site([]))
    app.load_site(ADDRESS)                        # nothing saved yet -> full retries
    app.load_site(ADDRESS)                        # saved copy exists -> quick
    app.load_site(ADDRESS, quick_if_saved=False)  # warm_cache.py -> full retries
    assert calls == [False, True, False]


def test_quick_mode_gives_every_source_one_short_try(monkeypatch):
    import requests
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append(timeout)
        raise requests.Timeout("stalled")
    monkeypatch.setattr(requests, "get", fake_get)
    token = sources.QUICK.set(True)
    try:
        with pytest.raises(sources.SourceError):
            sources.ground_elevation(40.35, -73.97)  # normally 3 tries x 8 s
    finally:
        sources.QUICK.reset(token)
    assert seen == [config.QUICK_TIMEOUT]
    seen.clear()
    with pytest.raises(sources.SourceError):
        sources.ground_elevation(40.35, -73.97)  # not quick: full retries
    assert seen == [config.USGS_TIMEOUT] * (config.USGS_RETRIES + 1)


def test_cache_key_ignores_case_punctuation_and_spaces():
    assert app.cache_path("1167 OCEAN AVE., Sea  Bright, NJ, 07760") == app.cache_path(ADDRESS)


def test_saved_gauge_curve_used_when_live_curve_fails(cache_dir, sample_site):
    brief.save_curve("8536110", sample_site["gauge"]["curve"])
    saved = brief.load_curve("8536110")
    assert saved and len(saved["curve"]) == 22
    assert brief.load_curve("8518750") is None  # nothing saved for The Battery


# ---------------------------------------------------------------------------
# Brief wording and fallbacks
# ---------------------------------------------------------------------------
def test_pct_small_values():
    assert brief.pct(0.002) == "<1%"
    assert brief.pct(0) == "0%"
    assert brief.pct(0.005) == "1%"  # half rounds up, like JS Math.round


def test_headline_compares_f_to_f_plus_2(sample_site):
    b = brief.build_brief(sample_site, years=30, freeboard_ft=2.0, start_year=2026)
    fb = {x["feet"]: x["chance"] for x in b["odds"]["freeboard"]}
    assert sorted(fb) == [0, 2, 3, 4, 5]  # f..f+3 plus the 0 ft row
    assert (f"Raising the lowest floor from 2 ft to 4 ft above the base flood elevation cuts "
            f"the 30-year odds from {brief.pct(fb[2])} to {brief.pct(fb[4])}.") in map(brief.plain, b["headline"])
    assert any(f"At 2 ft above the base flood elevation the 30-year odds are about {brief.pct(fb[2])}"
               in brief.plain(q) for q in b["questions"])
    # and each number carries the right label
    assert ("[[2 ft|assumed]] to [[4 ft|assumed]]" in b["headline"][2]
            and f"[[{brief.pct(fb[4])}|modeled]]" in b["headline"][2])
    assert b["freeboard_applied"] is True


def test_one_year_grammar(sample_site):
    b = brief.build_brief(sample_site, years=1, start_year=2026)
    assert brief.plain(b["headline"][0]).startswith("Over 1 year,")


def test_curve_without_one_percent_falls_back(sample_site):
    site = copy.deepcopy(sample_site)
    site["gauge"]["curve"] = [c for c in site["gauge"]["curve"] if c[0] > 0.02]
    b = brief.build_brief(site, years=30, freeboard_ft=2.0, start_year=2026)  # no ValueError
    assert b["odds"]["scenarios"] == {} and b["odds"]["freeboard"] == []
    assert brief.plain(b["headline"][0]).startswith(
        "Over 30 years, the chance of at least one major flood is about 26%")
    assert any("doesn't reach the 1% level" in brief.plain(w) for w in b["warnings"])
    assert "Floor height only changes the odds for coastal sites." in b["warnings"]


def test_floor_height_warning_for_inland_site(sample_site):
    site = copy.deepcopy(sample_site)
    site["fema"] = {"zone": "X", "subtype": "AREA OF MINIMAL FLOOD HAZARD", "in_sfha": False,
                    "bfe_ft": None, "datum": None}
    site["ground_ft"], site["gauge"]["miles"] = 47.0, 30.8
    b = brief.build_brief(site, freeboard_ft=2.0, start_year=2026)
    assert b["freeboard_applied"] is False
    assert "Floor height only changes the odds for coastal sites." in b["warnings"]


# ---------------------------------------------------------------------------
# Gemini number guardrail (Gemini is mocked; no network)
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_brief(sample_site):
    return brief.build_brief(sample_site, years=30, start_year=2026)


FAITHFUL = ("Over [[30 years|assumed]] the chance of a major flood is about [[26%|modeled]] on "
            "today's map and [[35%|modeled]] with sea-level rise. Raising the floor [[2 ft|assumed]] "
            "cuts that to [[8%|modeled]]. The [[100-year|assumed]] storm is [[9.2 in|measured]].")


def test_guardrail_rejects_invented_number(sample_brief, cache_dir, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(summary, "_generate", lambda prompt: (
        "Over [[30 years|assumed]] the chance of a major flood is about [[42%|modeled]]. "
        "That is high. Ask questions.", "fake-model"))
    r = summary.summarize(sample_brief, "en")
    assert r["ok"] is False and r["text"] == "Summary unavailable."
    assert "42" in r["reason"]
    assert not list(cache_dir.glob("summary_*.json"))  # rejected output is never cached


def test_guardrail_passes_faithful_summary(sample_brief, cache_dir, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(summary, "_generate", lambda prompt: (FAITHFUL, "fake-model"))
    r = summary.summarize(sample_brief, "en")
    assert r["ok"] is True and r["verified"] is True


@pytest.mark.parametrize("text, why", [
    (FAITHFUL.replace("[[26%|modeled]]", "26%"), "unlabeled 26"),
    (FAITHFUL.replace("[[9.2 in|measured]]", "[[9.2 in|modeled]]"), "[[9.2 in|modeled]]"),
    (FAITHFUL.replace("[[30 years|assumed]]", "[[30 years|measured]]"), "[[30 years|measured]]"),
])
def test_guardrail_rejects_missing_or_wrong_labels(sample_brief, cache_dir, monkeypatch, text, why):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(summary, "_generate", lambda prompt: (text, "fake-model"))
    r = summary.summarize(sample_brief, "en")
    assert r["ok"] is False and why in r["reason"]


def test_guardrail_number_parsing():
    src = {"chance": 0.3487, "rain": 8.91, "text": "a 53-year flood"}
    assert summary.unverified_numbers("35% / 34.9% / 8.9 in / 8,9 pulgadas / 53", src) == []
    assert summary.unverified_numbers("about 36% and 9.1 in", src) == ["36", "9.1"]


# ---------------------------------------------------------------------------
# No API key (public Vercel site): saved summaries only, Gemini never called
# ---------------------------------------------------------------------------
def test_no_key_serves_saved_summary_only(sample_brief, cache_dir, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(summary, "_generate", lambda prompt: (FAITHFUL, "fake-model"))
    assert summary.summarize(sample_brief, "en")["ok"] is True  # saved to cache

    monkeypatch.delenv("GEMINI_API_KEY")

    def must_not_call(prompt):
        raise AssertionError("Gemini called without a key")
    monkeypatch.setattr(summary, "_generate", must_not_call)
    assert summary.available() is True
    r = summary.summarize(sample_brief, "en")
    assert r["ok"] is True and r["cached"] is True

    other = dict(sample_brief, headline=sample_brief["headline"][:1])  # a different brief, not saved
    r = summary.summarize(other, "en")
    assert r["ok"] is False and r["text"] == "Summary unavailable."


def test_buttons_hidden_with_no_key_and_nothing_saved(cache_dir, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client = app.app.test_client()
    assert client.get("/api/features").get_json()["summary"] is False
    assert client.post("/api/summary", json={"brief": {}}).status_code == 404


def test_summary_cache_key_ignores_float_noise_between_machines():
    # macOS and Linux (Vercel) math can differ in the 16th digit; saved summaries must still match
    mac = {"odds": {"p_start": 0.010000000000000005, "chance": 35.0}}
    linux = {"odds": {"p_start": 0.010000000000000004, "chance": 35}}
    assert summary._cache_path(mac, "en", None) == summary._cache_path(linux, "en", None)


# ---------------------------------------------------------------------------
# Every number in the brief's text is labeled measured / modeled / assumed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kw", [{}, {"freeboard_ft": 2.0}, {"years": 1}])
def test_every_number_in_brief_text_is_labeled(sample_site, kw):
    b = brief.build_brief(sample_site, start_year=2026, **kw)
    for text in b["headline"] + b["questions"] + b["warnings"]:
        assert not any(ch.isdigit() for ch in brief.TAG_RE.sub("", text)), text


def test_inland_brief_text_is_labeled(sample_site):
    site = copy.deepcopy(sample_site)
    site["fema"] = {"zone": "X", "subtype": None, "in_sfha": False, "bfe_ft": None, "datum": None}
    site["ground_ft"], site["gauge"]["miles"] = 47.0, 30.8
    b = brief.build_brief(site, freeboard_ft=2.0, start_year=2026)
    for text in b["headline"] + b["questions"] + b["warnings"]:
        assert not any(ch.isdigit() for ch in brief.TAG_RE.sub("", text)), text
    assert "[[2021|measured]]" in b["questions"][0]  # Ida (2021)
