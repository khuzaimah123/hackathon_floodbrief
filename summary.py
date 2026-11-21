"""
Optional plain-English summary (and Spanish translation) of a brief, written by Gemini.

Guardrail: every number in the model's output must appear in the brief JSON it was
given (after rounding). If any number doesn't, the output is thrown away and the user
sees "Summary unavailable." The model never adds numbers to the brief.
"""
import hashlib
import json
import math
import os
import re

import config

UNAVAILABLE = "Summary unavailable."
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")

PROMPT_EN = """You are helping a volunteer member of a local zoning board who is not a flood expert.
Write a 3-sentence plain-English summary of the flood brief below.

Rules:
- Use only numbers that appear in the JSON. Do not calculate, combine or estimate new numbers.
- Write every number with digits (for example 35%, not "thirty-five percent").
- Plain text only: no markdown, no bullet points, no headings.
- Reply with only the 3 sentences, nothing before or after them.

Flood brief JSON:
{payload}"""

PROMPT_ES = """Translate this flood-risk summary into clear, plain Spanish for a volunteer zoning
board member. Keep every number exactly as written, with digits and a period for decimals.
Do not add, remove or change any numbers. Plain text only, no markdown.
Reply with only the translation, nothing before or after it.

Summary:
{text}"""


def enabled():
    """True when live Gemini calls are possible (an API key is set)."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def has_saved():
    """True when verified summaries are saved in cache/ (e.g. for the demo addresses)."""
    try:
        return any(n.startswith("summary_") and n.endswith(".json")
                   for n in os.listdir(config.CACHE_DIR))
    except OSError:
        return False


def available():
    """Show the summary buttons: live with a key, or saved-only without one (e.g. on Vercel)."""
    return enabled() or has_saved()


# ---------------------------------------------------------------------------
# Number guardrail
# ---------------------------------------------------------------------------
def _round_half_up(x, d):
    return math.floor(x * 10 ** d + 0.5) / 10 ** d


def _readings(token):
    """Possible (value, decimals) readings of a number token, e.g. '8,9' -> 8.9 or 89."""
    out = []
    plain = token.replace(",", "")  # comma as thousands separator: 1,000
    if plain.count(".") <= 1:
        out.append((float(plain), len(plain.split(".")[1]) if "." in plain else 0))
    if token.count(",") == 1 and "." not in token:  # comma as decimal point: 8,9
        out.append((float(token.replace(",", ".")), len(token.split(",")[1])))
    if token.count(".") >= 1 and "," not in token and all(len(p) == 3 for p in token.split(".")[1:]):
        out.append((float(token.replace(".", "")), 0))  # period as thousands: 1.000
    return out


def numbers_in(text):
    return NUM_RE.findall(text)


def allowed_numbers(obj):
    """Every number in a JSON value: numeric fields, plus numbers written inside strings/keys."""
    vals = []

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            vals.append(abs(float(o)))
        elif isinstance(o, str):
            for t in numbers_in(o):
                vals.extend(v for v, _ in _readings(t))
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(str(k))
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(obj)
    return vals


def _matches(value, decimals, allowed):
    for v in allowed:
        cands = [v, v * 100] if 0 < v <= 1 else [v]  # probabilities may be written as percents
        for c in cands:
            for r in (_round_half_up(c, decimals), round(c, decimals)):
                if abs(r - value) < 1e-9:
                    return True
    return False


def unverified_numbers(text, source):
    """Numbers in `text` that don't appear in `source` (JSON value). Empty list = passes."""
    allowed = allowed_numbers(source)
    bad = []
    for t in numbers_in(text):
        readings = _readings(t)
        if not readings or not any(_matches(v, d, allowed) for v, d in readings):
            bad.append(t)
    return bad


# ---------------------------------------------------------------------------
# Gemini call (with model fallback) and a cache of verified summaries
# ---------------------------------------------------------------------------
def model_payload(brief):
    """What the model sees: the brief minus app status messages (warnings)."""
    return {k: v for k, v in brief.items() if k != "warnings"}


def _canon(o):
    """JSON that hashes the same after a browser round trip (JS turns 35.0 into 35)."""
    if isinstance(o, float) and o.is_integer():
        return int(o)
    if isinstance(o, dict):
        return {k: _canon(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_canon(v) for v in o]
    return o


def _cache_path(payload, lang, text):
    blob = json.dumps(_canon([payload, lang, text]), sort_keys=True)
    key = hashlib.sha1(blob.encode()).hexdigest()[:16]
    return os.path.join(config.CACHE_DIR, f"summary_{key}.json")


def _generate(prompt):
    """Try each model in turn; return (text, model) or raise the last error."""
    from google import genai  # imported here so the app runs without the SDK installed
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_S * 1000))
    models = [os.environ.get("GEMINI_MODEL") or config.GEMINI_MODELS[0]] + config.GEMINI_MODELS[1:]
    last = None
    for model in dict.fromkeys(models):  # de-duplicate, keep order
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2))
            if r.text and r.text.strip():
                return r.text.strip(), model
            last = RuntimeError(f"{model} returned no text")
        except Exception as e:  # 503 high demand, 429 quota, timeouts: try the next model
            last = e
    raise last


def summarize(brief, lang="en", english_text=None):
    """
    lang="en": 3-sentence summary of the brief.
    lang="es": Spanish translation of `english_text` (a summary that already passed).
    Either way the output's numbers are checked against the brief before it is returned.
    """
    payload = model_payload(brief)
    if lang == "es":
        if not english_text:
            return {"ok": False, "text": UNAVAILABLE, "reason": "No English summary to translate."}
        prompt = PROMPT_ES.format(text=english_text)
    else:
        prompt = PROMPT_EN.format(payload=json.dumps(payload, indent=1))

    path = _cache_path(payload, lang, english_text if lang == "es" else None)
    try:
        with open(path) as f:
            saved = json.load(f)
        return {"ok": True, "verified": True, "text": saved["text"], "model": saved["model"],
                "cached": True}
    except (OSError, ValueError, KeyError):
        pass

    if not enabled():  # no key (e.g. the public Vercel site): saved summaries only
        return {"ok": False, "text": UNAVAILABLE,
                "reason": "No GEMINI_API_KEY; only saved summaries are available."}
    try:
        text, model = _generate(prompt)
    except Exception as e:
        return {"ok": False, "text": UNAVAILABLE, "reason": f"Gemini error: {type(e).__name__}: {e}"[:300]}

    bad = unverified_numbers(text, payload)
    if bad:
        return {"ok": False, "text": UNAVAILABLE, "model": model,
                "reason": f"Discarded: numbers not in the brief: {', '.join(bad)}"}
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump({"lang": lang, "model": model, "text": text}, f)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
    return {"ok": True, "verified": True, "text": text, "model": model, "cached": False}
