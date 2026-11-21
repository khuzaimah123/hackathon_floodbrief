"""
Flood Brief: run with `python3 app.py`, then open http://localhost:5050

Every lookup where geocode, FEMA and ground elevation succeed is saved to cache/.
If the internet drops (or a live lookup comes back with more warnings than the saved
copy), the app serves the saved copy for that address. Run `python3 warm_cache.py`
before judging to pre-load the demo addresses.
Run with SAMPLE=1 to use the built-in sample site (no internet needed at all).
"""
import hashlib
import json
import os
import re
import time

from flask import Flask, jsonify, request, send_from_directory

import brief
import config
import sources

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = config.CACHE_DIR
os.makedirs(CACHE, exist_ok=True)
app = Flask(__name__, static_folder="static")


def cache_key(address):
    """Lowercase, punctuation -> space, whitespace collapsed: 'Ave.,  NJ' == 'ave nj'."""
    return " ".join(re.sub(r"[^\w\s]", " ", address.lower()).split())


def cache_path(address):
    key = hashlib.sha1(cache_key(address).encode()).hexdigest()[:16]
    return os.path.join(CACHE, f"{key}.json")


def read_json(path):
    """Contents of a JSON file, or None if it is missing or unreadable."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_json(path, data):
    """Write via a temp file so an interrupted save never leaves a broken cache file."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def is_cacheable(site):
    """Geocode, FEMA and ground elevation all succeeded (rain/gauge are optional)."""
    return site.get("fema") is not None and site.get("ground_ft") is not None


def from_cache(saved):
    site = saved["site"]
    site["warnings"] = list(site.get("warnings", [])) + [f"Using data saved {saved['saved_at']}."]
    site["from_cache"] = saved["saved_at"]
    return site


def load_site(address):
    if os.environ.get("SAMPLE") == "1":
        with open(os.path.join(HERE, "sample_site.json")) as f:
            return json.load(f)
    path = cache_path(address)
    saved = read_json(path)
    try:
        site = brief.fetch_site(address)
    except sources.SourceError:
        if saved:
            return from_cache(saved)
        raise
    if saved:
        saved_count = saved.get("warning_count", len(saved["site"].get("warnings", [])))
        if len(site["warnings"]) > saved_count:  # live lookup is worse than what we have
            return from_cache(saved)
    if is_cacheable(site):
        write_json(path, {"saved_at": time.strftime("%Y-%m-%d %H:%M"), "address": address,
                          "warning_count": len(site["warnings"]), "site": site})
    return site


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/demo-addresses")
def api_demo_addresses():
    return jsonify(config.DEMO_ADDRESSES)


@app.get("/api/brief")
def api_brief():
    address = (request.args.get("address") or "").strip()
    if not address and os.environ.get("SAMPLE") != "1":
        return jsonify({"error": "Enter an address."}), 400
    try:
        years = max(1, min(int(request.args.get("years", 30)), 100))
        freeboard = max(0.0, min(float(request.args.get("freeboard", 0)), 10.0))
    except ValueError:
        return jsonify({"error": "Years and freeboard must be numbers."}), 400
    try:
        site = load_site(address)
    except sources.SourceError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(brief.build_brief(site, years=years, freeboard_ft=freeboard))


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5050)))
