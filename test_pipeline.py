import pandas as pd

import pipeline as p


def make_record(uuid="abc123", **bedwars):
    stats = {field: 0 for field in p.COUNTERS}
    stats.update(bedwars)
    return {
        "ingested_at": "20260919T120000Z",
        "requested_name": "TestPlayer",
        "payload": {
            "success": True,
            "player": {
                "uuid": uuid,
                "displayname": "TestPlayer",
                "achievements": {"bedwars_level": 42},
                "stats": {"Bedwars": stats},
            },
        },
    }


def test_ratio_treats_zero_denominator_as_one():
    out = p.ratio(pd.Series([10, 6]), pd.Series([0, 3]))
    assert out.tolist() == [10.0, 2.0]


def test_flatten_extracts_bedwars_fields():
    row = p.flatten(make_record(wins_bedwars=5, games_played_bedwars=9))
    assert row["uuid"] == "abc123"
    assert row["wins_bedwars"] == 5
    assert row["bedwars_level"] == 42


def test_flatten_handles_player_who_never_joined():
    record = {"ingested_at": "20260919T120000Z", "payload": {"success": True, "player": None}}
    row = p.flatten(record)
    assert row["uuid"] is None
    assert row["wins_bedwars"] == 0


def test_flatten_defaults_missing_bedwars_stats_to_zero():
    record = make_record()
    record["payload"]["player"]["stats"] = {}
    row = p.flatten(record)
    assert all(row[field] == 0 for field in p.COUNTERS)


def test_validate_quarantines_bad_rows():
    good_row = p.flatten(make_record(wins_bedwars=5, games_played_bedwars=9))
    negative = p.flatten(make_record(uuid="neg", kills_bedwars=-1))
    impossible = p.flatten(make_record(uuid="imp", wins_bedwars=10, games_played_bedwars=2))
    no_uuid = p.flatten(make_record(uuid=None))

    df = pd.DataFrame([good_row, negative, impossible, no_uuid])
    good, bad = p.validate(df)

    assert good["uuid"].tolist() == ["abc123"]
    assert len(bad) == 3
