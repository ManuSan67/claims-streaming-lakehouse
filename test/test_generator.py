import pandas as pd

from src.generator import build, ring_workshops

data = build()


def test_same_seed_same_data():
    again = build()
    for name, df in data.items():
        pd.testing.assert_frame_equal(df, again[name])


def test_policy_changes():
    cdc = data["policies_cdc"]
    assert cdc["policy_id"].nunique() == 8000
    assert (cdc["op"] == "INSERT").sum() == 8000
    assert set(cdc["op"]) == {"INSERT", "UPDATE", "DELETE"}


def test_duplicate_events_about_one_percent():
    ev = data["claim_events"]
    share = ev["event_id"].duplicated().mean()
    assert 0.005 < share < 0.015


def test_channel_starts_in_april():
    ev = data["claim_events"]
    before = ev[pd.to_datetime(ev["arrival_date"]) < "2026-04-01"]
    assert before["channel"].isna().all()
    assert ev["channel"].notna().any()


def test_fraud_ring_in_guadalajara():
    ring = set(ring_workshops(data["workshops"]))
    fraud = data["investigations"].query("outcome == 'fraud'")
    ev = data["claim_events"].drop_duplicates("claim_id")
    shops = ev[ev["claim_id"].isin(fraud["claim_id"])]["workshop_id"]
    assert len(ring) == 8
    assert shops.isin(ring).mean() > 0.8