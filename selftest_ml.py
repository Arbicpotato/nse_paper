"""Offline check of the v2 ML code on synthetic data: python selftest_ml.py"""
import json
import os
import sys
import tempfile
import types

import numpy as np
import pandas as pd

cfg = json.load(open("config.json"))
src = os.getcwd()
sys.path.insert(0, src)
os.chdir(tempfile.mkdtemp())                     # keep real data/ untouched
rng = np.random.default_rng(0)


def daily(seed, n=800):
    r = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-11-20", periods=n, tz="Asia/Kolkata")
    vol = 0.012 + 0.01 * np.abs(np.sin(np.arange(n) / 30))           # slow volatility waves
    close = 100 * np.exp(np.cumsum(r.normal(0, vol)))
    op = np.r_[close[0], close[:-1]] * (1 + r.normal(0, 0.002, n))
    hi = np.maximum(op, close) * (1 + np.abs(r.normal(0, vol / 2)))
    lo = np.minimum(op, close) * (1 - np.abs(r.normal(0, vol / 2)))
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                         "volume": r.integers(4e6, 8e6, n)}, index=idx)


stub = types.ModuleType("data")
stub.fetch = lambda sym, interval, period: daily(abs(hash(sym)) % 1000 + 1)
sys.modules["data"] = stub
import db, ml                                      # noqa: E402

# --- picker model end to end
ml.train_picker(cfg)
assert os.path.exists("data/models/picker.joblib")
nd, d = daily(7), {s: daily(abs(hash(s)) % 1000 + 1) for s in cfg["universe"][:12]}
top = ml.model_picks(cfg, d, nd, "2026-11-24")
assert top and len(top) == cfg["picks_per_night"], top

# --- trade scorer end to end: outcome weakly depends on relvol
c = db.connect()
rows = []
for i in range(600):
    f = dict(gap=rng.normal(0, .005), or_pct=rng.uniform(.003, .02), atr_pct=rng.uniform(.002, .008),
             relvol=rng.uniform(1, 3), rsi=rng.uniform(55, 72), vwap_dist=rng.uniform(0, .01),
             nifty_ret=rng.normal(0, .003), hour=rng.uniform(9.5, 14.4))
    win = rng.random() < 0.35 + 0.1 * (f["relvol"] - 1)
    rows.append(dict(date=str(pd.Timestamp("2026-06-01") + pd.Timedelta(days=i // 5)), symbol=f"S{i % 20}",
                     side="LONG", rule_version="v1", status="closed", risk_rs=10.0, charges=1.0,
                     net=8.0 if win else -11.0, features=json.dumps(f)))
db.save_trades(c, rows, "shadow")
ml.train_trade_scorer(cfg, c)
assert os.path.exists("data/models/trade_scorer.joblib")
out = ml.score_trades(c, "2026-11-23", [{**rows[0], "symbol": "S1"}])
assert len(out) == 1 and 0 <= out[0][1] <= 1
print("selftest_ml ok")
