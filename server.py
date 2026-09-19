"""Local web server for the Bedwars dashboard.

Serves the static frontend and a small JSON API built on pipeline.py.

Run:
    python server.py
Then open http://127.0.0.1:8000

The server only listens on your own machine (127.0.0.1). The browser never talks
to Hypixel directly, so your API key is only used server side.
"""

import json
import os
import re
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory

import pipeline as p

MAX_PLAYERS = 10
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{3,16}")
STATIC_DIR = Path(__file__).parent / "static"

SUMMARY_COLS = [
    "uuid", "username", "snapshot_ts", "bedwars_level", "games_played_bedwars",
    "win_rate", "wlr", "fkdr", "kdr", "bblr",
]
HISTORY_COLS = [
    "uuid", "username", "snapshot_ts", "bedwars_level", "games_played_bedwars", "fkdr", "wlr",
]
PROGRESS_COLS = [
    "uuid", "username", "snapshot_ts", "games_played_bedwars_delta", "wins_bedwars_delta",
    "final_kills_bedwars_delta", "final_deaths_bedwars_delta", "fkdr_period", "wlr_period",
]

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


def dashboard_payload():
    if not has_data():
        return {"empty": True}

    clean = p.build_clean()
    bad = read_quarantine()
    if clean.empty:
        return {
            "empty": False, "summary": [], "history": [], "progress": [],
            "quality": quality_payload(clean, bad),
        }

    latest, progress = p.build_metrics(clean)

    history = clean.sort_values("snapshot_ts").copy()
    history["fkdr"] = p.ratio(history["final_kills_bedwars"], history["final_deaths_bedwars"])
    history["wlr"] = p.ratio(history["wins_bedwars"], history["losses_bedwars"])

    return {
        "empty": False,
        "summary": records(latest.sort_values("fkdr", ascending=False)[SUMMARY_COLS]),
        "history": records(history[HISTORY_COLS]),
        "progress": records(progress.sort_values("snapshot_ts", ascending=False)[PROGRESS_COLS]),
        "quality": quality_payload(clean, bad),
    }


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/config")
def config():
    return jsonify(server_has_key=bool(os.environ.get("HYPIXEL_API_KEY")))


@app.get("/api/dashboard")
def dashboard():
    return jsonify(dashboard_payload())


@app.post("/api/fetch")
def fetch():
    body = request.get_json(silent=True) or {}
    raw_names = body.get("usernames", [])
    names = [n.strip() for n in raw_names if isinstance(n, str) and n.strip()]

    api_key = request.headers.get("X-Hypixel-Key") or os.environ.get("HYPIXEL_API_KEY", "")
    if not api_key:
        return jsonify(error="No API key. Enter one in the form or set HYPIXEL_API_KEY."), 400
    if not names:
        return jsonify(error="Enter at least one username."), 400
    if len(names) > MAX_PLAYERS:
        return jsonify(error=f"Keep it to {MAX_PLAYERS} players per fetch to stay under the rate limit."), 400

    valid = [n for n in names if USERNAME_RE.fullmatch(n)]
    invalid = [n for n in names if not USERNAME_RE.fullmatch(n)]
    if not valid:
        return jsonify(error="None of those look like valid Minecraft usernames (3 to 16 letters, numbers, or underscores)."), 400

    result = p.ingest(valid, api_key)
    skipped = [{"name": n, "reason": r} for n, r in result["skipped"]]
    skipped += [{"name": n, "reason": "not a valid Minecraft username"} for n in invalid]
    return jsonify(saved=result["saved"], skipped=skipped)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
