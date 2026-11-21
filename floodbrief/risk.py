"""
The math. No network calls here, so it is easy to test and explain.
"""
import math


def chance_of_at_least_one(annual_probs):
    """P(at least one flood) = 1 - (1-p1)(1-p2)...(1-pN)."""
    no_flood = 1.0
    for p in annual_probs:
        no_flood *= (1.0 - p)
    return 1.0 - no_flood


def fixed_chance(p, years):
    """The simple version: 1 - (1-p)^N."""
    return 1.0 - (1.0 - p) ** years


# ---------------------------------------------------------------------------
# Sea-level rise path
# ---------------------------------------------------------------------------
def slr_feet(year, scenario, baseline_year=2005):
    """
    Sea-level rise (ft) above the baseline year, following a smooth curve through
    the scenario's 2050 and 2100 values: s(t) = b*t + c*t^2, t = years since baseline.
    A quadratic captures the fact that rise is speeding up.
    """
    t50, t100 = 2050 - baseline_year, 2100 - baseline_year
    s50, s100 = scenario[2050], scenario[2100]
    # Solve b*t50 + c*t50^2 = s50 and b*t100 + c*t100^2 = s100
    c = (s100 - s50 * t100 / t50) / (t100 ** 2 - t50 * t100)
    b = (s50 - c * t50 ** 2) / t50
    t = year - baseline_year
    return b * t + c * t * t


def additional_rise(year, start_year, scenario, baseline_year=2005):
    """Rise between start_year (today) and year."""
    return slr_feet(year, scenario, baseline_year) - slr_feet(start_year, scenario, baseline_year)


# ---------------------------------------------------------------------------
# Flood-frequency curve: water level <-> annual chance
# ---------------------------------------------------------------------------
def prob_at_level(curve, level):
    """
    Annual chance that water exceeds `level`, read off a gauge curve
    [(p, level), ...]. Interpolates log(p) linearly between points.
    Above the top of the curve, extends the last segment's slope (a labeled estimate).
    """
    pts = sorted(curve, key=lambda x: x[1])  # ascending level
    if level <= pts[0][1]:
        return min(pts[0][0], 0.99)
    for (p1, h1), (p2, h2) in zip(pts, pts[1:]):
        if h1 <= level <= h2:
            frac = (level - h1) / (h2 - h1)
            return math.exp(math.log(p1) + frac * (math.log(p2) - math.log(p1)))
    (p1, h1), (p2, h2) = pts[-2], pts[-1]
    slope = (math.log(p2) - math.log(p1)) / (h2 - h1)
    return math.exp(math.log(p2) + slope * (level - h2))


def level_at_prob(curve, p_target):
    """Water level with annual chance p_target (inverse of prob_at_level)."""
    pts = sorted(curve, key=lambda x: x[0], reverse=True)  # p descending, level ascending
    for (p1, h1), (p2, h2) in zip(pts, pts[1:]):
        if p2 <= p_target <= p1:
            frac = (math.log(p_target) - math.log(p1)) / (math.log(p2) - math.log(p1))
            return h1 + frac * (h2 - h1)
    raise ValueError("probability outside curve range")


def coastal_annual_probs(curve, start_year, years, scenario, freeboard_ft=0.0):
    """
    Year-by-year flood chance for a fixed height at a coastal site.

    Anchor: FEMA's base flood elevation (BFE) has a 1% annual chance today.
    A floor built `freeboard_ft` above the BFE is that much higher on the curve.
    Sea-level rise of s ft makes a fixed height act like a height s ft lower today.
    """
    anchor = level_at_prob(curve, 0.01)
    probs = []
    for i in range(years):
        year = start_year + i
        s = additional_rise(year, start_year, scenario)
        probs.append(min(prob_at_level(curve, anchor + freeboard_ft - s), 0.99))
    return probs


def return_period(p):
    return 1.0 / p if p > 0 else float("inf")


# ---------------------------------------------------------------------------
# Rainfall: how often today's 100-year storm happens in the future
# ---------------------------------------------------------------------------
def _interp_factor(factors, T):
    """Change factor for return period T, interpolating in log(T); held flat outside."""
    ks = sorted(factors)
    if T <= ks[0]:
        return factors[ks[0]]
    if T >= ks[-1]:
        return factors[ks[-1]]
    for a, b in zip(ks, ks[1:]):
        if a <= T <= b:
            f = (math.log(T) - math.log(a)) / (math.log(b) - math.log(a))
            return factors[a] + f * (factors[b] - factors[a])


def future_return_period(depths, factors, T_today=100):
    """
    depths: {return period: 24-hr depth today (in)} from NOAA Atlas 14.
    factors: {2: f, 10: f, 100: f} county change factors.
    Returns (today's depth, future depth of that same storm, future return period of today's depth).
    """
    Ts = sorted(depths)
    target = depths[T_today]
    future = [(T, depths[T] * _interp_factor(factors, T)) for T in Ts]
    for (T1, d1), (T2, d2) in zip(future, future[1:]):
        if d1 <= target <= d2:
            f = (target - d1) / (d2 - d1)
            T_new = math.exp(math.log(T1) + f * (math.log(T2) - math.log(T1)))
            return target, depths[T_today] * _interp_factor(factors, T_today), T_new
    return target, depths[T_today] * _interp_factor(factors, T_today), None
