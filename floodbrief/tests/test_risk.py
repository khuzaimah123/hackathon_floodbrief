import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import risk  # noqa: E402


def test_fixed_100yr_over_mortgage():
    assert round(risk.fixed_chance(0.01, 30), 4) == 0.2603


def test_fixed_matches_general_formula():
    assert abs(risk.fixed_chance(0.01, 30) - risk.chance_of_at_least_one([0.01] * 30)) < 1e-12


def test_rising_probability_example():
    probs = [0.01] * 10 + [0.02] * 10 + [0.04] * 10
    assert round(risk.chance_of_at_least_one(probs), 4) == 0.5087


def test_hundred_year_not_certain_in_100_years():
    assert round(risk.fixed_chance(0.01, 100), 2) == 0.63


def test_slr_path_hits_projection_points():
    s = config.SLR_SCENARIOS["central"]
    assert abs(risk.slr_feet(2050, s) - 1.3) < 1e-9
    assert abs(risk.slr_feet(2100, s) - 3.0) < 1e-9
    assert risk.slr_feet(2005, s) == 0


def test_curve_round_trip():
    c = config.SANDY_HOOK_CURVE
    assert abs(risk.level_at_prob(c, 0.01) - 6.52) < 1e-9
    assert abs(risk.prob_at_level(c, 3.82) - 0.1) < 1e-9


def test_sea_level_rise_raises_odds_and_freeboard_lowers_them():
    c, s = config.SANDY_HOOK_CURVE, config.SLR_SCENARIOS["central"]
    base = risk.chance_of_at_least_one(risk.coastal_annual_probs(c, 2026, 30, s, 0))
    raised = risk.chance_of_at_least_one(risk.coastal_annual_probs(c, 2026, 30, s, 2))
    assert base > risk.fixed_chance(0.01, 30)
    assert raised < base


def test_first_year_is_one_percent():
    c, s = config.SANDY_HOOK_CURVE, config.SLR_SCENARIOS["high"]
    assert abs(risk.coastal_annual_probs(c, 2026, 5, s)[0] - 0.01) < 1e-9


def test_rain_storm_becomes_more_frequent():
    depths = {1: 2.8, 2: 3.4, 5: 4.4, 10: 5.2, 25: 6.4, 50: 7.4, 100: 8.5, 200: 9.7, 500: 11.4, 1000: 12.9}
    today, future, T = risk.future_return_period(depths, config.RAIN_CHANGE_FACTORS["Monmouth"])
    assert today == 8.5 and round(future, 2) == 10.71 and 10 < T < 100
