"""
Live smoke test: calls each data source in sources.py on its own and prints OK/FAIL,
the time it took, and the key values it returned.

    python3 smoke_test.py                       # default: Long Branch
    python3 smoke_test.py "1 Main St, Town, NJ"  # any address(es)
"""
import sys
import time

import requests

import config
import sources

DEFAULT_ADDRESS = "100 Ocean Ave, Long Branch, NJ 07740"
FEMA_LAYER_FIELDS = ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF", "STATIC_BFE", "V_DATUM"]


def run(label, fn, *args):
    t = time.time()
    try:
        value = fn(*args)
    except Exception as e:  # show any failure, not just SourceError
        print(f"  FAIL  {label:<18} {time.time() - t:5.1f}s  {type(e).__name__}: {e}")
        return None
    print(f"  OK    {label:<18} {time.time() - t:5.1f}s  {summarize(label, value)}")
    return value


def summarize(label, v):
    if label == "geocode":
        return f"{v['matched_address']} | lat {v['lat']:.5f}, lon {v['lon']:.5f} | county {v['county']}"
    if label == "fema_zone":
        return (f"zone {v['zone']} | subtype {v['subtype']} | in_sfha {v['in_sfha']} | "
                f"BFE {v['bfe_ft']} ft | datum {v['datum']}")
    if label == "ground_elevation":
        return f"{v:.2f} ft"
    if label == "atlas14_24hr":
        return ", ".join(f"{k}yr {d}in" for k, d in v.items())
    if label == "gauge_curve":
        p01 = [lvl for p, lvl in v if abs(p - 0.01) < 1e-9]
        return (f"{len(v)} points | p={v[0][0]} -> {v[0][1]} ft ... p={v[-1][0]} -> {v[-1][1]} ft"
                f" | 1% level: {p01[0] if p01 else 'MISSING'} ft")
    return repr(v)


def check_fema_layer():
    url = config.FEMA_NFHL_ZONES.rsplit("/query", 1)[0]
    print(f"FEMA layer check: {url}?f=json")
    t = time.time()
    try:
        d = requests.get(url, params={"f": "json"}, timeout=config.HTTP_TIMEOUT).json()
    except Exception as e:
        print(f"  FAIL  {time.time() - t:.1f}s  {e}")
        return
    fields = [f["name"] for f in d.get("fields", [])]
    missing = [f for f in FEMA_LAYER_FIELDS if f not in fields]
    status = "OK  " if d.get("name") == "Flood Hazard Zones" and not missing else "FAIL"
    print(f"  {status}  {time.time() - t:.1f}s  layer name: {d.get('name')!r}")
    print(f"        fields: {', '.join(fields)}")
    if missing:
        print(f"        MISSING: {', '.join(missing)}")


def smoke(address):
    print(f"\n=== {address}")
    g = run("geocode", sources.geocode, address)
    if g is None:
        print("  (skipping the rest: no coordinates)")
        return
    lat, lon = g["lat"], g["lon"]
    run("fema_zone", sources.fema_zone, lat, lon)
    run("ground_elevation", sources.ground_elevation, lat, lon)
    run("atlas14_24hr", sources.atlas14_24hr, lat, lon)
    sid, gauge, miles = sources.nearest_gauge(lat, lon)
    print(f"  --    nearest_gauge            {sid} {gauge['name']} ({miles:.1f} mi)")
    run("gauge_curve", sources.gauge_curve, sid)


if __name__ == "__main__":
    check_fema_layer()
    for addr in sys.argv[1:] or [DEFAULT_ADDRESS]:
        smoke(addr)
