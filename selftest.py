"""Offline checks: python selftest.py   (no network needed)"""
import json

import numpy as np
import pandas as pd

import engine
from costs import charges, round_trip

v3 = json.load(open("config.json"))
cfg = {**v3, "max_cost_to_risk": 9, "stop_atr_min": 0.5, "stop_atr_max": 2.0}   # v1 behaviour for the original checks

# --- cost model vs the design doc's rough scale
assert 80 <= charges(1000, 1000, 100) <= 86, charges(1000, 1000, 100)      # Rs 1 lakh position
assert 1.0 <= charges(100, 100, 10) <= 1.2, charges(100, 100, 10)          # Rs 1,000 position
assert round_trip(100, 100, 10, 1) == round_trip(100, 100, 10, -1)


# --- synthetic days
def make(day3):
    """2 flat days + a third whose first 3 bars are flat and the rest follow `day3` closes."""
    rows, price = [], 100.0
    for d in ["2026-11-19", "2026-11-20", "2026-11-23"]:
        ts = pd.date_range(f"{d} 09:15", periods=75, freq="5min", tz="Asia/Kolkata")
        for k, t in enumerate(ts):
            close = 100 + 0.15 * (-1) ** k
            vol = 1000
            if d == "2026-11-23" and k >= 3:
                close = day3[k - 3] if k - 3 < len(day3) else day3[-1]
                vol = 3000 if k == 3 else 1000
            rows.append((t, price, max(price, close) + 0.1, min(price, close) - 0.1, close, vol))
            price = close
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")


day = pd.Timestamp("2026-11-23").date()
up = make([100.9, 101.4, 101.9, 102.4, 102.8])
tr, note = engine.simulate_day(up, day, cfg)
assert tr and tr["side"] == "LONG" and tr["exit_reason"] == "target", (tr, note)
assert tr["net"] > 0 and tr["charges"] > 0 and tr["entry_time"] > tr["trigger_time"]

down = make([100.9, 100.5, 100.0, 99.6, 99.2])
tr, note = engine.simulate_day(down, day, cfg)
assert tr and tr["exit_reason"] == "stop" and tr["net"] < 0, (tr, note)

flat = make([100.0, 100.15])
tr, note = engine.simulate_day(flat, day, cfg)
assert tr is None and note == "no trigger", (tr, note)

# live mode must not see the future: at 09:32 the trigger bar (09:30) is not complete yet
now = pd.Timestamp("2026-11-23 09:32", tz="Asia/Kolkata")
tr, note = engine.simulate_day(up, day, cfg, now=now)
assert tr is None, (tr, note)

# day limits: two identical-time winners, max 1 trade allowed
bars = {"A": up, "B": up}
kept, _ = engine.run_day(day, ["A", "B"], bars, {**cfg, "max_trades_per_day": 1})
assert len(kept) == 1
# v3: cost gate blocks the same trade when costs are too large a share of risk
tr, note = engine.simulate_day(up, day, v3)
assert tr is None and note.startswith("skipped: costs"), (tr, note)

# pre-prepped frames give identical results
assert engine.simulate_day(engine.prep(up), day, cfg, prepped=True)[0] == engine.simulate_day(up, day, cfg)[0]
print("selftest ok")
