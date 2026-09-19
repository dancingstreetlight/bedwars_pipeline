"""Hypixel Bedwars stats pipeline: raw (JSON snapshots) -> clean (validated table) -> metrics (calculated stats).

Setup:
    pip install -r requirements.txt
    export HYPIXEL_API_KEY=your_key_here     (Windows PowerShell: $env:HYPIXEL_API_KEY="your_key_here")

Usage:
    python pipeline.py ingest Name1 Name2 Name3
    python pipeline.py transform

Run "ingest" on a schedule (daily is enough) so the clean and metrics layers build up history.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

DATA = Path("data")
RAW = DATA / "raw"
CLEAN = DATA / "clean"
METRICS = DATA / "metrics"

TS_FORMAT = "%Y%m%dT%H%M%SZ"

COUNTERS = [
    "games_played_bedwars",
    "wins_bedwars",
    "losses_bedwars",
    "kills_bedwars",
    "deaths_bedwars",
    "final_kills_bedwars",
    "final_deaths_bedwars",
    "beds_broken_bedwars",
    "beds_lost_bedwars",
]


# ---------------------------------------------------------------- Raw layer

def get_uuid(name):
    """Resolve a Minecraft username to a UUID using the Mojang API."""
    resp = requests.get(
        f"https://api.mojang.com/users/profiles/minecraft/{name}", timeout=10
    )
    if resp.status_code in (204, 404):
        raise ValueError(f"no such Minecraft account: {name}")
    resp.raise_for_status()
    return resp.json()["id"]


def fetch_player(uuid, api_key):
    """Fetch the raw player document from the Hypixel API."""
    resp = requests.get(
        "https://api.hypixel.net/v2/player",
        params={"uuid": uuid},
        headers={"API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"Hypixel API error: {data.get('cause')}")
    return data


def ingest(names, api_key):
    """Save one untouched JSON snapshot per player. The raw layer is append only.

    Returns {"saved": [names], "skipped": [(name, reason)]}.
    """
    results = {"saved": [], "skipped": []}
    for name in names:
        try:
            uuid = get_uuid(name)
            payload = fetch_player(uuid, api_key)
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            print(f"skipped {name}: {exc}")
            results["skipped"].append((name, str(exc)))
            continue

        ts = datetime.now(timezone.utc).strftime(TS_FORMAT)
        folder = RAW / uuid
        folder.mkdir(parents=True, exist_ok=True)
        record = {"ingested_at": ts, "requested_name": name, "payload": payload}
        (folder / f"{ts}.json").write_text(json.dumps(record))
        print(f"saved {name} at {ts}")
        results["saved"].append(name)
        time.sleep(1)  # stay well under the API rate limit
    return results


# ---------------------------------------------------------------- Clean layer

def load_raw():
    return [json.loads(p.read_text()) for p in sorted(RAW.glob("*/*.json"))]


def flatten(record):
    """Turn one raw record into one flat row."""
    player = record["payload"].get("player") or {}
    bedwars = (player.get("stats") or {}).get("Bedwars") or {}
    row = {
        "uuid": player.get("uuid"),
        "username": player.get("displayname"),
        "snapshot_ts": record["ingested_at"],
        "bedwars_level": (player.get("achievements") or {}).get("bedwars_level"),
    }
    for field in COUNTERS:
        row[field] = bedwars.get(field, 0)
    return row


def validate(df):
    """Split rows into (good, bad). Bad rows go to a quarantine table."""
    ok = (
        df["uuid"].notna()
        & (df[COUNTERS] >= 0).all(axis=1)  # NaN fails this check too
        & (df["wins_bedwars"] <= df["games_played_bedwars"])
    )
    return df[ok].copy(), df[~ok].copy()


def build_clean():
    rows = [flatten(r) for r in load_raw()]
    if not rows:
        raise SystemExit("No raw data found. Run the ingest step first.")

    df = pd.DataFrame(rows)
    df[COUNTERS] = df[COUNTERS].apply(pd.to_numeric, errors="coerce")
    df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], format=TS_FORMAT, utc=True)
    df = df.drop_duplicates(["uuid", "snapshot_ts"])

    good, bad = validate(df)
    CLEAN.mkdir(parents=True, exist_ok=True)
    good.to_parquet(CLEAN / "bedwars_snapshots.parquet", index=False)
    quarantine_path = CLEAN / "quarantine.parquet"
    if len(bad):
        bad.to_parquet(quarantine_path, index=False)
    else:
        quarantine_path.unlink(missing_ok=True)
    print(f"clean: {len(good)} good rows, {len(bad)} quarantined")
    return good


# ---------------------------------------------------------------- Metrics layer

def ratio(num, den):
    """Bedwars convention: a zero denominator is treated as 1."""
    return (num / den.where(den != 0, 1)).round(2)


def build_metrics(clean):
    df = clean.sort_values(["uuid", "snapshot_ts"]).reset_index(drop=True)

    # Lifetime summary from each player's latest snapshot
    latest = df.groupby("uuid").tail(1).copy()
    latest["wlr"] = ratio(latest["wins_bedwars"], latest["losses_bedwars"])
    latest["fkdr"] = ratio(latest["final_kills_bedwars"], latest["final_deaths_bedwars"])
    latest["kdr"] = ratio(latest["kills_bedwars"], latest["deaths_bedwars"])
    latest["bblr"] = ratio(latest["beds_broken_bedwars"], latest["beds_lost_bedwars"])
    latest["win_rate"] = (latest["wins_bedwars"] / latest["games_played_bedwars"].where(
        latest["games_played_bedwars"] != 0, 1)).round(3)

    # Progress between consecutive snapshots (what changed since last time)
    deltas = df.groupby("uuid")[COUNTERS].diff().add_suffix("_delta")
    progress = df[["uuid", "username", "snapshot_ts"]].join(deltas)
    progress = progress.dropna(subset=[f"{COUNTERS[0]}_delta"])
    progress["fkdr_period"] = ratio(
        progress["final_kills_bedwars_delta"], progress["final_deaths_bedwars_delta"]
    )
    progress["wlr_period"] = ratio(
        progress["wins_bedwars_delta"], progress["losses_bedwars_delta"]
    )

    METRICS.mkdir(parents=True, exist_ok=True)
    latest.to_parquet(METRICS / "player_summary.parquet", index=False)
    progress.to_parquet(METRICS / "player_progress.parquet", index=False)
    print(f"metrics: {len(latest)} players, {len(progress)} progress rows")
    return latest, progress


# ---------------------------------------------------------------- CLI

def main(argv):
    if len(argv) < 2 or argv[1] not in ("ingest", "transform"):
        raise SystemExit(__doc__)

    if argv[1] == "ingest":
        api_key = os.environ.get("HYPIXEL_API_KEY")
        if not api_key:
            raise SystemExit("Set the HYPIXEL_API_KEY environment variable first.")
        if len(argv) < 3:
            raise SystemExit("Give at least one username: python pipeline.py ingest Name1 Name2")
        ingest(argv[2:], api_key)
    else:
        latest, _ = build_metrics(build_clean())
        cols = ["username", "bedwars_level", "games_played_bedwars", "wlr", "fkdr", "bblr"]
        print(latest[cols].sort_values("fkdr", ascending=False).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv)
