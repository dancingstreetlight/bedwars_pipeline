import json

import pytest

import pipeline as p
import server
from test_pipeline import make_record


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A test client whose data folders live in a temp directory."""
    monkeypatch.setattr(p, "DATA", tmp_path)
    monkeypatch.setattr(p, "RAW", tmp_path / "raw")
    monkeypatch.setattr(p, "CLEAN", tmp_path / "clean")
    monkeypatch.setattr(p, "METRICS", tmp_path / "metrics")
    monkeypatch.delenv("HYPIXEL_API_KEY", raising=False)
    return server.app.test_client()


def write_snapshot(uuid, name, ts, **bedwars):
    record = make_record(uuid=uuid, **bedwars)
    record["ingested_at"] = ts
    record["payload"]["player"]["displayname"] = name
    folder = p.RAW / uuid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{ts}.json").write_text(json.dumps(record))


def test_index_page_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Bedwars Stats" in res.data


def test_dashboard_reports_empty_when_no_data(client):
    assert client.get("/api/dashboard").get_json() == {"empty": True}


def test_dashboard_with_history_and_quarantine(client):
    for i, ts in enumerate(["20260901T120000Z", "20260902T120000Z"]):
        write_snapshot(
            "aaa", "PlayerA", ts,
            wins_bedwars=10 + 3 * i, losses_bedwars=10, games_played_bedwars=20 + 5 * i,
            final_kills_bedwars=30 + 9 * i, final_deaths_bedwars=10 + 2 * i,
        )
    write_snapshot("bad", "Broken", "20260903T120000Z", kills_bedwars=-1)

    data = client.get("/api/dashboard").get_json()

    assert data["empty"] is False
    overall = data["modes"]["overall"]
    assert [r["username"] for r in overall["summary"]] == ["PlayerA"]
    assert len(overall["history"]) == 2
    assert len(overall["progress"]) == 1
    assert data["quality"]["passed"] == 2
    assert data["quality"]["quarantined"] == 1
    assert data["quality"]["players"] == 1
    assert data["quality"]["quarantined_rows"][0]["uuid"] == "bad"


def test_dashboard_when_every_row_fails_validation(client):
    write_snapshot("bad", "Broken", "20260903T120000Z", kills_bedwars=-1)
    data = client.get("/api/dashboard").get_json()
    assert data["modes"]["overall"]["summary"] == []
    assert data["quality"]["quarantined"] == 1


def test_fetch_requires_a_key(client):
    res = client.post("/api/fetch", json={"usernames": ["SomeName"]})
    assert res.status_code == 400
    assert "API key" in res.get_json()["error"]


def test_fetch_requires_usernames(client):
    res = client.post("/api/fetch", json={"usernames": []}, headers={"X-Hypixel-Key": "k"})
    assert res.status_code == 400


def test_fetch_rejects_too_many_players(client):
    names = [f"Player{i:02d}" for i in range(server.MAX_PLAYERS + 1)]
    res = client.post("/api/fetch", json={"usernames": names}, headers={"X-Hypixel-Key": "k"})
    assert res.status_code == 400


def test_fetch_rejects_invalid_usernames(client):
    res = client.post("/api/fetch", json={"usernames": ["../etc", "a b"]}, headers={"X-Hypixel-Key": "k"})
    assert res.status_code == 400


def test_fetch_passes_valid_names_to_ingest_and_reports_skips(client, monkeypatch):
    calls = {}

    def fake_ingest(names, api_key):
        calls["names"], calls["key"] = names, api_key
        return {"saved": ["GoodName"], "skipped": [("Ghost", "no such Minecraft account: Ghost")]}

    monkeypatch.setattr(p, "ingest", fake_ingest)
    res = client.post(
        "/api/fetch",
        json={"usernames": ["GoodName", "Ghost", "bad name!"]},
        headers={"X-Hypixel-Key": "secret"},
    )
    body = res.get_json()

    assert res.status_code == 200
    assert calls == {"names": ["GoodName", "Ghost"], "key": "secret"}
    assert body["saved"] == ["GoodName"]
    reasons = {s["name"]: s["reason"] for s in body["skipped"]}
    assert "Ghost" in reasons and reasons["bad name!"] == "not a valid Minecraft username"


def test_server_environment_key_is_ignored(client, monkeypatch):
    monkeypatch.setenv("HYPIXEL_API_KEY", "from_env")
    res = client.post("/api/fetch", json={"usernames": ["SomeName"]})
    assert res.status_code == 400
    assert "API key" in res.get_json()["error"]


def test_live_returns_dashboard_and_writes_nothing(client, monkeypatch):
    server._live_cache.clear()
    monkeypatch.setattr(p, "fetch_snapshot", lambda name, key: ("u1", make_record(
        uuid="u1", wins_bedwars=5, losses_bedwars=5, games_played_bedwars=10,
        final_kills_bedwars=20, final_deaths_bedwars=10)))
    res = client.post("/api/live", json={"usernames": ["GoodName"]}, headers={"X-Hypixel-Key": "k"})
    body = res.get_json()

    assert res.status_code == 200
    assert body["fetched"] == ["GoodName"]
    assert body["dashboard"]["modes"]["overall"]["summary"][0]["fkdr"] == 2.0
    assert not p.DATA.joinpath("raw").exists()
    assert not p.CLEAN.exists() and not p.METRICS.exists()


def test_live_caches_repeat_lookups(client, monkeypatch):
    server._live_cache.clear()
    calls = []
    monkeypatch.setattr(p, "fetch_snapshot", lambda name, key: calls.append(name) or ("u1", make_record(uuid="u1")))
    for _ in range(2):
        client.post("/api/live", json={"usernames": ["GoodName"]}, headers={"X-Hypixel-Key": "k"})
    assert calls == ["GoodName"]


def test_live_reports_error_when_nothing_fetched(client, monkeypatch):
    server._live_cache.clear()
    def boom(name, key):
        raise ValueError("no such Minecraft account: Ghost")
    monkeypatch.setattr(p, "fetch_snapshot", boom)
    res = client.post("/api/live", json={"usernames": ["Ghost"]}, headers={"X-Hypixel-Key": "k"})
    assert res.status_code == 502
    assert res.get_json()["skipped"][0]["name"] == "Ghost"


def test_dashboard_splits_stats_by_game_mode(client):
    write_snapshot(
        "aaa", "PlayerA", "20260901T120000Z",
        games_played_bedwars=30, wins_bedwars=20, final_kills_bedwars=50,
        eight_one_games_played_bedwars=10, eight_one_wins_bedwars=4, eight_one_final_kills_bedwars=12,
        eight_two_games_played_bedwars=20, eight_two_wins_bedwars=16, eight_two_final_kills_bedwars=38,
    )
    modes = client.get("/api/dashboard").get_json()["modes"]

    assert set(modes) == {"overall", "solo", "doubles", "trios", "fours"}
    assert modes["overall"]["summary"][0]["final_kills_bedwars"] == 50
    assert modes["solo"]["summary"][0]["final_kills_bedwars"] == 12
    assert modes["doubles"]["summary"][0]["wins_bedwars"] == 16
    assert modes["trios"]["summary"][0]["games_played_bedwars"] == 0
    assert "beds_broken_bedwars" in modes["solo"]["summary"][0]


def test_mode_with_more_wins_than_games_is_quarantined(client):
    write_snapshot("aaa", "PlayerA", "20260901T120000Z", eight_one_wins_bedwars=5, eight_one_games_played_bedwars=2)
    assert client.get("/api/dashboard").get_json()["quality"]["quarantined"] == 1
