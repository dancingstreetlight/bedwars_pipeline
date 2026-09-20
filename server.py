"""Local web server for the Bedwars dashboard.

Serves the static frontend and a small JSON API built on pipeline.py.

Run:
    python server.py
Then open http://127.0.0.1:8000

The server only listens on your own machine (127.0.0.1). The browser never talks
to Hypixel directly, so your API key is only used server side.
"""

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests
from flask import Flask, jsonify, request, send_from_directory

import pipeline as p

MAX_PLAYERS = 10
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{3,16}")
STATIC_DIR = Path(__file__).parent / "static"

SUMMARY_COLS = [
    "uuid", "username", "snapshot_ts", "bedwars_level",
    "games_played_bedwars", "wins_bedwars", "losses_bedwars", "win_rate", "wlr",
    "final_kills_bedwars", "final_deaths_bedwars", "fkdr",
    "kills_bedwars", "deaths_bedwars", "kdr",
    "beds_broken_bedwars", "beds_lost_bedwars", "bblr",
]
HISTORY_COLS = ["uuid", "username", "snapshot_ts", "bedwars_level"] + p.COUNTERS + ["fkdr", "wlr", "kdr", "bblr"]
PROGRESS_COLS = (
    ["uuid", "username", "snapshot_ts"]
    + [f"{c}_delta" for c in p.COUNTERS]
    + ["fkdr_period", "wlr_period"]
)

LIVE_TTL_SECONDS = 120
_live_cache = {}  # lowercase username -> (fetched_at, uuid, raw_record). Memory only, cleared on restart.

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")


def records(df):
    """DataFrame to a list of plain dicts (NaN becomes null, timestamps become ISO strings)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def has_data():
    return any(p.RAW.glob("*/*.json"))


def read_quarantine():
    path = p.CLEAN / "quarantine.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def quality_payload(clean, bad):
    rows = records(bad[["uuid", "username", "snapshot_ts"] + p.COUNTERS]) if len(bad) else []
    return {
        "passed": int(len(clean)),
        "quarantined": int(len(bad)),
        "players": int(clean["uuid"].nunique()),
        "quarantined_rows": rows,
    }


EMPTY_MODE = {"summary": [], "history": [], "progress": []}


def mode_payload(clean, mode, write):
    latest, progress = p.build_metrics(clean, write=write, mode=mode)

    history = p.add_ratios(p.mode_view(clean, mode).sort_values("snapshot_ts"))

    return {
        "summary": records(latest.sort_values("fkdr", ascending=False)[SUMMARY_COLS]),
        "history": records(history[HISTORY_COLS]),
        "progress": records(progress.sort_values("snapshot_ts", ascending=False)[PROGRESS_COLS]),
    }


def build_payload(clean, bad, write):
    """Shared by the saved dashboard and live mode. write=False means no files are touched."""
    if clean.empty:
        modes = {m: EMPTY_MODE for m in p.MODES}
    else:
        modes = {m: mode_payload(clean, m, write) for m in p.MODES}
    return {"empty": False, "modes": modes, "quality": quality_payload(clean, bad)}


def dashboard_payload():
    if not has_data():
        return {"empty": True}
    clean = p.build_clean()
    return build_payload(clean, read_quarantine(), write=True)


def fetch_live(name, api_key):
    """Return (uuid, raw_record) for a player, reusing a recent fetch to protect the rate limit."""
    cached = _live_cache.get(name.lower())
    if cached and time.time() - cached[0] < LIVE_TTL_SECONDS:
        return cached[1], cached[2]
    uuid, record = p.fetch_snapshot(name, api_key)
    _live_cache[name.lower()] = (time.time(), uuid, record)
    return uuid, record


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/dashboard")
def dashboard():
    return jsonify(dashboard_payload())


def parse_request():
    """Validate the request body. Returns (valid, invalid, api_key, error_response)."""
    body = request.get_json(silent=True) or {}
    raw_names = body.get("usernames", [])
    names = [n.strip() for n in raw_names if isinstance(n, str) and n.strip()]

    api_key = request.headers.get("X-Hypixel-Key", "")
    api_key = api_key.strip().strip("\"'")  # tolerate stray spaces or quotes from copy and paste
    if not api_key:
        return None, None, None, (jsonify(error="Enter your Hypixel API key."), 400)
    if not names:
        return None, None, None, (jsonify(error="Enter at least one username."), 400)
    if len(names) > MAX_PLAYERS:
        return None, None, None, (jsonify(error=f"Keep it to {MAX_PLAYERS} players per fetch to stay under the rate limit."), 400)

    valid = [n for n in names if USERNAME_RE.fullmatch(n)]
    invalid = [n for n in names if not USERNAME_RE.fullmatch(n)]
    if not valid:
        return None, None, None, (jsonify(error="None of those look like valid Minecraft usernames (3 to 16 letters, numbers, or underscores)."), 400)
    return valid, invalid, api_key, None


@app.post("/api/fetch")
def fetch():
    """Fetch and SAVE snapshots to the data folder."""
    valid, invalid, api_key, error = parse_request()
    if error:
        return error

    result = p.ingest(valid, api_key)
    skipped = [{"name": n, "reason": r} for n, r in result["skipped"]]
    skipped += [{"name": n, "reason": "not a valid Minecraft username"} for n in invalid]
    return jsonify(saved=result["saved"], skipped=skipped)


@app.post("/api/live")
def live():
    """Fetch and return a dashboard payload WITHOUT writing anything to disk."""
    valid, invalid, api_key, error = parse_request()
    if error:
        return error

    records_, fetched, skipped = [], [], []
    for name in valid:
        try:
            _, record = fetch_live(name, api_key)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            skipped.append({"name": name, "reason": str(exc)})
            continue
        records_.append(record)
        fetched.append(name)
    skipped += [{"name": n, "reason": "not a valid Minecraft username"} for n in invalid]

    if not records_:
        return jsonify(error="Nothing could be fetched.", skipped=skipped), 502

    clean, bad = p.clean_records(records_)
    return jsonify(fetched=fetched, skipped=skipped, dashboard=build_payload(clean, bad, write=False))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
