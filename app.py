"""
Flood Brief: run with `python3 app.py`, then open http://localhost:5050

Every successful lookup is saved to cache/. If the internet drops during the demo,
the app automatically serves the saved copy for that address.
Run with SAMPLE=1 to use the built-in sample site (no internet needed at all).
"""
import hashlib
import json
import os
import time

from flask import Flask, jsonify, request, send_from_directory

import brief
import sources

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)
app = Flask(__name__, static_folder="static")


def cache_path(address):
    key = hashlib.sha1(address.strip().lower().encode()).hexdigest()[:16]
    return os.path.join(CACHE, f"{key}.json")


def load_site(address):
    if os.environ.get("SAMPLE") == "1":
        with open(os.path.join(HERE, "sample_site.json")) as f:
            return json.load(f)
    path = cache_path(address)
    try:
        site = brief.fetch_site(address)
        if not site["warnings"]:  # only cache complete lookups
            with open(path, "w") as f:
                json.dump({"saved_at": time.strftime("%Y-%m-%d %H:%M"), "site": site}, f)
        return site
    except sources.SourceError:
        if os.path.exists(path):
            with open(path) as f:
                saved = json.load(f)
            site = saved["site"]
            site["warnings"] = [f"Offline: using data saved {saved['saved_at']}."]
            return site
        raise


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


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
