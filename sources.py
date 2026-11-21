"""
Live data fetchers. Each function returns plain Python data or raises SourceError.
"""
import math
import re

import requests

import config


class SourceError(Exception):
    pass


def _get(url, params):
    try:
        r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        raise SourceError(f"{url} failed: {e}") from e


def geocode(address):
    """Address -> lat, lon, matched address, county name (Census Geocoder)."""
    r = _get(config.CENSUS_GEOCODER, {
        "address": address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "layers": "Counties",
        "format": "json",
    })
    matches = r.json().get("result", {}).get("addressMatches", [])
    if not matches:
        raise SourceError("Address not found. Try including city, state and ZIP.")
    m = matches[0]
    county = None
    counties = m.get("geographies", {}).get("Counties", [])
    if counties:
        county = counties[0].get("BASENAME") or counties[0].get("NAME", "").replace(" County", "")
    return {
        "lat": m["coordinates"]["y"],
        "lon": m["coordinates"]["x"],
        "matched_address": m.get("matchedAddress", address),
        "county": county,
    }


def fema_zone(lat, lon):
    """FEMA flood zone and base flood elevation at a point (National Flood Hazard Layer)."""
    r = _get(config.FEMA_NFHL_ZONES, {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM",
        "returnGeometry": "false",
        "f": "json",
    })
    data = r.json()
    if "error" in data:
        raise SourceError(f"FEMA error: {data['error']}")
    feats = data.get("features", [])
    if not feats:
        return {"zone": None, "subtype": None, "in_sfha": False, "bfe_ft": None, "datum": None}
    a = feats[0]["attributes"]
    bfe = a.get("STATIC_BFE")
    if bfe is None or bfe <= -9000:  # FEMA uses -9999 for "no BFE"
        bfe = None
    return {
        "zone": a.get("FLD_ZONE"),
        "subtype": a.get("ZONE_SUBTY"),
        "in_sfha": a.get("SFHA_TF") == "T",
        "bfe_ft": bfe,
        "datum": a.get("V_DATUM"),
    }


def ground_elevation(lat, lon):
    """Ground elevation in feet (USGS 3DEP Elevation Point Query Service)."""
    r = _get(config.USGS_ELEVATION, {"x": lon, "y": lat, "wkid": 4326, "units": "Feet",
                                     "includeDate": "false"})
    try:
        v = float(r.json()["value"])
    except (KeyError, ValueError, TypeError) as e:
        raise SourceError("USGS elevation returned no value") from e
    if v < -1000:  # no-data sentinel
        raise SourceError("USGS elevation has no data here")
    return v


def atlas14_24hr(lat, lon):
    """NOAA Atlas 14 24-hour rainfall depths (inches) by return period."""
    r = _get(config.NOAA_ATLAS14_CSV, {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}",
                                       "data": "depth", "units": "english", "series": "pds"})
    aris, row = None, None
    for line in r.text.splitlines():
        if "ARI (years)" in line:
            aris = [int(float(x)) for x in re.findall(r"\d+(?:\.\d+)?", line.split(":", 1)[1])]
        elif line.strip().startswith("24-hr"):
            row = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", line.split(":", 1)[1])]
    if not aris or not row or len(aris) != len(row):
        raise SourceError("Could not parse NOAA Atlas 14 response")
    return dict(zip(aris, row))


def gauge_curve(station_id):
    """Flood-frequency curve [(p, level_ft), ...] for a NOAA tide gauge."""
    r = _get(config.NOAA_EXTREME_LEVELS, {"name": "extremewaterlevels", "station": station_id,
                                          "details": "exceedancelevels", "levelType": "high",
                                          "units": "english"})
    levels = (r.json().get("GEV_HI") or {}).get("exceedanceLevels") or []
    curve = [(float(x["probability"]), float(x["level"])) for x in levels]
    if len(curve) < 5:
        raise SourceError(f"No exceedance curve for station {station_id}")
    return curve


def miles_between(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_gauge(lat, lon):
    best = min(config.GAUGES.items(),
               key=lambda kv: miles_between(lat, lon, kv[1]["lat"], kv[1]["lon"]))
    sid, g = best
    return sid, g, miles_between(lat, lon, g["lat"], g["lon"])
