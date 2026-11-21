"""
All the numbers the app relies on, in one place, with sources.
If a judge asks "where does that come from?", the answer is in this file.
"""
import os

# ---------------------------------------------------------------------------
# NOAA tide gauges used for coastal sites (CO-OPS Extreme Water Levels product)
# ---------------------------------------------------------------------------
GAUGES = {
    "8531680": {"name": "Sandy Hook, NJ", "lat": 40.4669, "lon": -74.0094},
    "8518750": {"name": "The Battery, NY", "lat": 40.7006, "lon": -74.0142},
    "8534720": {"name": "Atlantic City, NJ", "lat": 39.3567, "lon": -74.4181},
    "8536110": {"name": "Cape May, NJ", "lat": 38.9683, "lon": -74.9600},
}

# Fallback flood-frequency curve for Sandy Hook, used only if the live API is down.
# Source: NOAA CO-OPS Derived Product API, extremewaterlevels / exceedancelevels,
# station 8531680, high levels, feet above MHHW (retrieved Nov 2026).
# Format: (annual exceedance probability, water level in ft)
SANDY_HOOK_CURVE = [
    (0.99, 1.67), (0.909, 1.92), (0.8, 2.09), (0.667, 2.27), (0.5, 2.51),
    (0.4, 2.69), (0.313, 2.88), (0.25, 3.05), (0.2, 3.23), (0.156, 3.43),
    (0.125, 3.62), (0.1, 3.82), (0.08, 4.03), (0.063, 4.27), (0.05, 4.49),
    (0.04, 4.73), (0.031, 5.01), (0.025, 5.28), (0.02, 5.56), (0.016, 5.88),
    (0.013, 6.19), (0.01, 6.52),
]

# A site counts as "coastal" (sea-level rise applies) if FEMA says so, or if it is
# within this distance of a gauge AND low-lying.
COASTAL_MAX_MILES = 25
COASTAL_MAX_GROUND_FT = 15

# ---------------------------------------------------------------------------
# Sea-level rise projections for New Jersey (feet above the 2005 baseline)
# Source: NJ Science & Technical Advisory Panel (STAP), Rutgers, Nov 2025 summary.
#   2050 likely range: 0.9 - 1.7 ft
#   2100 likely range (intermediate emissions, no rapid ice loss): 2.2 - 3.8 ft
# "central" is the midpoint of the likely range (the report gives no median).
# ---------------------------------------------------------------------------
SLR_SCENARIOS = {
    "low":     {2050: 0.9, 2100: 2.2},
    "central": {2050: 1.3, 2100: 3.0},
    "high":    {2050: 1.7, 2100: 3.8},
}
SLR_BASELINE_YEAR = 2005

# ---------------------------------------------------------------------------
# NJDEP future precipitation change factors (24-hour design storms, by county)
# Source: NJ Stormwater Management rule amendments (2023), N.J.A.C. 7:8.
# These are for 2050-2099, upper likely value, moderate emissions (RCP 4.5).
# Multiply a NOAA Atlas 14 depth by the factor to get the future depth.
# ---------------------------------------------------------------------------
RAIN_CHANGE_FACTORS = {  # county: {return period (yrs): factor}
    "Atlantic":   {2: 1.22, 10: 1.24, 100: 1.39},
    "Bergen":     {2: 1.20, 10: 1.23, 100: 1.37},
    "Burlington": {2: 1.17, 10: 1.18, 100: 1.32},
    "Camden":     {2: 1.18, 10: 1.22, 100: 1.39},
    "Cape May":   {2: 1.21, 10: 1.24, 100: 1.32},
    "Cumberland": {2: 1.20, 10: 1.21, 100: 1.39},
    "Essex":      {2: 1.19, 10: 1.22, 100: 1.33},
    "Gloucester": {2: 1.19, 10: 1.23, 100: 1.41},
    "Hudson":     {2: 1.19, 10: 1.19, 100: 1.23},
    "Hunterdon":  {2: 1.19, 10: 1.23, 100: 1.42},
    "Mercer":     {2: 1.16, 10: 1.17, 100: 1.36},
    "Middlesex":  {2: 1.19, 10: 1.21, 100: 1.33},
    "Monmouth":   {2: 1.19, 10: 1.19, 100: 1.26},
    "Morris":     {2: 1.23, 10: 1.28, 100: 1.46},
    "Ocean":      {2: 1.18, 10: 1.19, 100: 1.24},
    "Passaic":    {2: 1.21, 10: 1.27, 100: 1.50},
    "Salem":      {2: 1.20, 10: 1.23, 100: 1.32},
    "Somerset":   {2: 1.19, 10: 1.24, 100: 1.48},
    "Sussex":     {2: 1.24, 10: 1.29, 100: 1.50},
    "Union":      {2: 1.20, 10: 1.23, 100: 1.35},
    "Warren":     {2: 1.20, 10: 1.25, 100: 1.37},
}

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
CENSUS_GEOCODER = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
FEMA_NFHL_ZONES = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
USGS_ELEVATION = "https://epqs.nationalmap.gov/v1/json"
NOAA_ATLAS14_CSV = "https://hdsc.nws.noaa.gov/cgi-bin/hdsc/new/fe_text_mean.csv"
NOAA_EXTREME_LEVELS = "https://api.tidesandcurrents.noaa.gov/dpapi/prod/webapi/product.json"

HTTP_TIMEOUT = 20  # seconds; FEMA can be slow
# USGS EPQS usually answers in 1-7 s but sometimes stalls past 20 s (seen in the Nov 2026
# smoke test). A stalled request rarely recovers, so retry with a shorter timeout instead.
USGS_TIMEOUT = 8   # seconds per try
USGS_RETRIES = 2   # extra tries after the first (3 total, worst case ~24 s)

# Saved lookups and gauge curves (committed to git so the demo works offline).
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

# ---------------------------------------------------------------------------
# Demo addresses (the "Try:" buttons and warm_cache.py use exactly these strings)
# Sea Bright + Keansburg: coastal AE zones, ground ~4-5 ft below the BFE.
# Manville: inland, outside the FEMA floodplain, flooded by Ida (2021).
# ---------------------------------------------------------------------------
DEMO_ADDRESSES = [
    "1167 Ocean Ave, Sea Bright, NJ 07760",
    "275 Beachway Ave, Keansburg, NJ 07734",
    "325 N Main St, Manville, NJ 08835",
]
