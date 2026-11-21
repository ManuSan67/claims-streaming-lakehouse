import numpy as np
import pandas as pd

START = pd.Timestamp("2026-01-01")
END = pd.Timestamp("2026-06-30 23:59:59")
HAIL_DAY = pd.Timestamp("2026-04-22")
CHANNEL_FROM = pd.Timestamp("2026-04-01")
RING_FROM = pd.Timestamp("2026-03-01")

CITIES = [
    ("CDMX", "Ciudad de Mexico", 0.30),
    ("JAL", "Guadalajara", 0.15),
    ("NL", "Monterrey", 0.15),
    ("MEX", "Toluca", 0.10),
    ("PUE", "Puebla", 0.08),
    ("QRO", "Queretaro", 0.07),
    ("GTO", "Leon", 0.08),
    ("YUC", "Merida", 0.07),
]

PLANS = {
    "AMPLIA": ["DM", "RT", "RC", "GM", "CR"],
    "LIMITADA": ["RT", "RC", "GM"],
    "BASICA": ["RC"],
}
RATES = {"AMPLIA": 0.045, "LIMITADA": 0.025, "BASICA": 0.012}

COVERAGE_NAMES = {
    "DM": ("Danos materiales", 0.05),
    "RT": ("Robo total", 0.10),
    "RC": ("Responsabilidad civil", 0.0),
    "GM": ("Gastos medicos ocupantes", 0.0),
    "CR": ("Cristales", 0.20),
}

CAUSES = {
    "colision": ("DM", 0.55, 9.6),
    "vandalismo": ("DM", 0.17, 8.6),
    "cristales": ("CR", 0.15, 8.2),
    "robo": ("RT", 0.08, 11.8),
    "inundacion": ("DM", 0.03, 10.1),
    "granizo": ("DM", 0.02, 10.0),
}


def _seed(rng):
    return int(rng.integers(1 << 31))


def _pick_city(rng, n):
    w = np.array([c[2] for c in CITIES])
    return rng.choice(len(CITIES), size=n, p=w / w.sum())


def coverages():
    rows = [(plan, code, *COVERAGE_NAMES[code]) for plan, codes in PLANS.items() for code in codes]
    return pd.DataFrame(rows, columns=["plan", "coverage_code", "coverage_name", "deductible_pct"])


def workshops(rng, n=240):
    idx = _pick_city(rng, n)
    return pd.DataFrame({
        "workshop_id": [f"W{i:04d}" for i in range(1, n + 1)],
        "workshop_name": [f"Taller {i:04d}" for i in range(1, n + 1)],
        "state": [CITIES[i][0] for i in idx],
        "city": [CITIES[i][1] for i in idx],
        "network": rng.choice(["agencia", "multimarca"], size=n, p=[0.35, 0.65]),
        "opened_date": pd.Timestamp("2010-01-01") + pd.to_timedelta(rng.integers(0, 5000, n), unit="D"),
    })


def ring_workshops(ws):
    return sorted(ws.loc[ws["city"] == "Guadalajara", "workshop_id"])[:8]


def policies(rng, n=8000):
    idx = _pick_city(rng, n)
    value = np.round(rng.lognormal(12.6, 0.4, n), -3)
    plan = rng.choice(list(PLANS), size=n, p=[0.6, 0.3, 0.1])
    return pd.DataFrame({
        "policy_id": [f"P{i:06d}" for i in range(1, n + 1)],
        "customer_id": [f"C{i:06d}" for i in rng.permutation(n) + 1],
        "plan": plan,
        "vehicle_year": rng.integers(2012, 2027, n),
        "vehicle_value": value,
        "annual_premium": np.round(value * pd.Series(plan).map(RATES).to_numpy(), 2),
        "state": [CITIES[i][0] for i in idx],
        "city": [CITIES[i][1] for i in idx],
        "start_date": pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 530, n), unit="D"),
    })


def policy_changes(pol, rng):
    ins = pol.assign(op="INSERT", change_ts=pol["start_date"] + pd.to_timedelta(rng.integers(8, 20, len(pol)), unit="h"))

    upd = pol.sample(frac=0.25, random_state=_seed(rng)).copy()
    upd["change_ts"] = upd["start_date"] + pd.to_timedelta(rng.integers(20, 300, len(upd)), unit="D")
    bump = rng.random(len(upd)) < 0.5
    upd.loc[bump, "plan"] = "AMPLIA"
    upd.loc[~bump, "vehicle_value"] = np.round(upd.loc[~bump, "vehicle_value"] * 1.12, -3)
    upd["annual_premium"] = np.round(upd["vehicle_value"] * upd["plan"].map(RATES), 2)
    upd["op"] = "UPDATE"

    dele = pol.drop(upd.index).sample(frac=0.05, random_state=_seed(rng)).copy()
    dele["change_ts"] = dele["start_date"] + pd.to_timedelta(rng.integers(30, 330, len(dele)), unit="D")
    dele["op"] = "DELETE"

    out = pd.concat([ins, upd, dele], ignore_index=True)
    out = out[out["change_ts"] <= END].copy()
    out["arrival_date"] = out["change_ts"].dt.normalize().clip(lower=START).dt.strftime("%Y-%m-%d")
    return out.sort_values("change_ts").reset_index(drop=True)


def _claim_rows(pol, shops_by_city, rng, loss_ts, causes):
    shop = [None if c == "robo" else rng.choice(shops_by_city[city]) for c, city in zip(causes, pol["city"])]
    return pd.DataFrame({
        "policy_id": pol["policy_id"].to_numpy(),
        "state": pol["state"].to_numpy(),
        "city": pol["city"].to_numpy(),
        "cause": causes,
        "coverage_code": [CAUSES[c][0] for c in causes],
        "workshop_id": shop,
        "loss_ts": loss_ts,
        "estimate": np.round(rng.lognormal(np.array([CAUSES[c][2] for c in causes]), 0.5), 2),
    })


def claims(pol, ws, rng, per_day=30):
    shops = ws.groupby("city")["workshop_id"].apply(list).to_dict()
    names = list(CAUSES)
    probs = np.array([CAUSES[c][1] for c in names])
    parts = []
    for day in pd.date_range(START, END.normalize()):
        k = int(rng.poisson(per_day))
        p = pol[pol["start_date"] <= day].sample(k, replace=True, random_state=_seed(rng))
        ts = day + pd.to_timedelta(rng.integers(0, 86400, k), unit="s")
        parts.append(_claim_rows(p, shops, rng, ts, rng.choice(names, size=k, p=probs / probs.sum())))

    cdmx = pol[(pol["city"] == "Ciudad de Mexico") & (pol["start_date"] <= HAIL_DAY)]
    p = cdmx.sample(1200, random_state=_seed(rng))
    ts = HAIL_DAY + pd.Timedelta(hours=15) + pd.to_timedelta(rng.integers(0, 6 * 3600, 1200), unit="s")
    hail = _claim_rows(p, shops, rng, ts, np.array(["granizo"] * 1200))
    hail["estimate"] = np.round(rng.uniform(15000, 60000, 1200), 2)
    parts.append(hail)

    gdl = pol[pol["city"] == "Guadalajara"]
    picks, days = [], []
    while len(picks) < 220:
        day = RING_FROM + pd.Timedelta(days=int(rng.integers(0, 122)))
        fresh = gdl[(gdl["start_date"] <= day) & (gdl["start_date"] > day - pd.Timedelta(days=60))]
        if len(fresh):
            picks.append(fresh.sample(1, random_state=_seed(rng)))
            days.append(day)
    p = pd.concat(picks)
    ts = pd.DatetimeIndex(days) + pd.to_timedelta(rng.integers(0, 86400, len(days)), unit="s")
    ring = _claim_rows(p, shops, rng, ts, np.array(["colision"] * len(days)))
    ring["workshop_id"] = rng.choice(ring_workshops(ws), size=len(ring))
    ring["estimate"] = np.round(ring["estimate"] * 2.5, 2)
    ring["is_fraud"] = True
    parts.append(ring)

    out = pd.concat(parts, ignore_index=True)
    out["is_fraud"] = out["is_fraud"].astype("boolean").fillna(False).astype(bool)
    out.loc[~out["is_fraud"] & (rng.random(len(out)) < 0.003), "is_fraud"] = True
    out = out.sort_values("loss_ts").reset_index(drop=True)
    out.insert(0, "claim_id", [f"S{i:07d}" for i in range(1, len(out) + 1)])
    out["source"] = np.where(rng.random(len(out)) < 0.3, "tpa", "app")
    out["channel"] = rng.choice(["app", "phone", "agent"], size=len(out), p=[0.5, 0.3, 0.2])
    return out


def events(cl, rng):
    n = len(cl)
    fnol = cl["loss_ts"] + pd.to_timedelta(rng.integers(600, 2 * 86400, n), unit="s")
    adj = fnol + pd.to_timedelta(rng.integers(1, 6, n), unit="D")
    paid_ok = rng.random(n) < 0.85
    pay = adj + pd.to_timedelta(rng.integers(3, 21, n), unit="D")
    close = pay.where(paid_ok, adj) + pd.to_timedelta(rng.integers(1, 6, n), unit="D")
    deductible = cl["coverage_code"].map({k: v[1] for k, v in COVERAGE_NAMES.items()})
    paid = np.round(cl["estimate"] * rng.uniform(0.8, 1.0, n) * (1 - deductible), 2)

    base = cl[["claim_id", "policy_id", "state", "city", "cause", "coverage_code", "workshop_id", "source", "channel"]]
    ev = pd.concat([
        base.assign(event_type="FNOL", event_ts=fnol, amount=np.nan, status="open"),
        base.assign(event_type="ADJUSTMENT", event_ts=adj, amount=cl["estimate"], status="open"),
        base[paid_ok].assign(event_type="PAYMENT", event_ts=pay[paid_ok], amount=paid[paid_ok], status="open"),
        base.assign(event_type="CLOSE", event_ts=close, amount=np.nan, status=np.where(paid_ok, "paid", "rejected")),
    ], ignore_index=True)
    ev = ev[ev["event_ts"] <= END].sort_values("event_ts").reset_index(drop=True)
    ev.insert(0, "event_id", [f"E{i:07d}" for i in range(1, len(ev) + 1)])

    lag = np.where(rng.random(len(ev)) < 0.04, rng.integers(1, 4, len(ev)), 0)
    ev["arrival_date"] = ev["event_ts"].dt.normalize() + pd.to_timedelta(lag, unit="D")
    dup = ev.sample(frac=0.01, random_state=_seed(rng))
    dup = dup.assign(arrival_date=dup["arrival_date"] + pd.Timedelta(days=1))
    ev = pd.concat([ev, dup], ignore_index=True)
    ev = ev[ev["arrival_date"] <= END].copy()
    ev.loc[ev["arrival_date"] < CHANNEL_FROM, "channel"] = None
    ev["arrival_date"] = ev["arrival_date"].dt.strftime("%Y-%m-%d")
    return ev.sort_values(["arrival_date", "event_ts"]).reset_index(drop=True)


def investigations(cl, rng):
    inv = pd.concat([cl[cl["is_fraud"]], cl[~cl["is_fraud"]].sample(600, random_state=_seed(rng))])
    inv = inv.assign(
        investigated_on=(inv["loss_ts"] + pd.to_timedelta(rng.integers(15, 60, len(inv)), unit="D")).dt.normalize(),
        outcome=np.where(inv["is_fraud"], "fraud", "legit"),
    )
    inv = inv[inv["investigated_on"] <= END]
    return inv[["claim_id", "investigated_on", "outcome"]].sort_values("investigated_on").reset_index(drop=True)


def build(seed=42):
    rng = np.random.default_rng(seed)
    ws = workshops(rng)
    pol = policies(rng)
    cdc = policy_changes(pol, rng)
    cl = claims(pol, ws, rng)
    return {
        "coverages": coverages(),
        "workshops": ws,
        "policies_cdc": cdc,
        "claim_events": events(cl, rng),
        "investigations": investigations(cl, rng),
    }