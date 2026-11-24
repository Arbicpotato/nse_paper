"""Parameter sweep on your saved bars. READ-ONLY: it never touches config.json, picks, log.db or live trades.

    python sweep.py            full grid (about 5-10 minutes)
    python sweep.py --quick    small grid (about 1-2 minutes)

How to read it: settings are ranked on the OLDER 60% of days only. The NEWER 40% is the honest test.
A setting is only interesting if it is positive in BOTH halves with a decent number of trades.
"""
import itertools
import json
import sys

import pandas as pd

import data
import engine

cfg0 = json.load(open("config.json"))
QUICK = "--quick" in sys.argv
ALT_SLIP = 0.0003                      # "what if real slippage is 0.03% per side" column

# --- indicators are the same for every setting, so compute them once per stock
_orig_prep, _cache = engine.prep, {}


def _prep_cached(df):
    if id(df) not in _cache:
        _cache[id(df)] = _orig_prep(df)
    return _cache[id(df)]


engine.prep = _prep_cached

NIFTY = data.load("NIFTY", "5m")
BARS = {s: (data.load(s, "5m"), data.load(s, "1m")) for s in cfg0["universe"]}
BARS = {s: b for s, b in BARS.items() if not b[0].empty}
print(f"{len(BARS)} stocks with saved 5-min bars")


def simulate(cfg):
    rows = []
    for sym, (df5, df1) in BARS.items():
        for day in sorted(set(df5.index.date))[3:]:
            tr, _ = engine.simulate_day(df5, day, cfg, NIFTY, df1)
            if tr and tr["status"] == "closed":
                rows.append({**tr, "symbol": sym})
    return pd.DataFrame(rows)


def summarize(t, cut, **tags):
    old, new = t[t.date < cut], t[t.date >= cut]
    lo = t.net + t.slip_rs * (1 - ALT_SLIP / cfg0["slippage"])        # same trades, lower slippage
    m = lambda x: x.net.mean() if len(x) else float("nan")
    return dict(**tags, n=len(t), n_old=len(old), n_new=len(new), win=(t.net > 0).mean(),
                net_old=m(old), net_new=m(new), net_all=t.net.mean(), net_all_lowslip=lo.mean())


if QUICK:
    GRID = dict(target_rr=[1.5, 2.0], stop_floor=[0.5, 1.0], min_relvol=[1.0, 1.5])
else:
    GRID = dict(target_rr=[1.0, 1.5, 2.0, 3.0], stop_floor=[0.5, 1.0, 1.5], min_relvol=[1.0, 1.5, 2.0])

combos = list(itertools.product(*GRID.values()))
results, cut = [], None
for i, vals in enumerate(combos, 1):
    p = dict(zip(GRID, vals))
    cfg = {**cfg0, **p, "stop_atr_min": p["stop_floor"], "stop_atr_max": p["stop_floor"] + 1.5, "max_cost_to_risk": 9}   # cost gate off, as in the v1 grid            # floor 0.5 -> cap 2.0 = your v1
    t = simulate(cfg)
    print(f"[{i}/{len(combos)}] {p}  trades={len(t)}", flush=True)
    if t.empty:
        continue
    if cut is None:                                                    # same date split for every setting
        dates = sorted(t.date.unique())
        cut = dates[int(len(dates) * 0.6)]
        print(f"older = before {cut}, newer = {cut} onward")
    for side in ("both", "LONG", "SHORT"):
        s = t if side == "both" else t[t.side == side]
        if len(s):
            results.append(summarize(s, cut, rr=p["target_rr"], floor=p["stop_floor"],
                                     relvol=p["min_relvol"], side=side))

R = pd.DataFrame(results)
if R.empty:
    sys.exit("No trades found. Is data/5m filled? Run: python main.py fetch")
R.round(3).to_csv("sweep_results.csv", index=False)
pd.set_option("display.width", 200)
cols = ["rr", "floor", "relvol", "side", "n_old", "n_new", "win", "net_old", "net_new", "net_all", "net_all_lowslip"]

base = R[(R.rr == 1.5) & (R.floor == 0.5) & (R.relvol == 1.0) & (R.side == "both")]
print("\n=== Your current v1 rules (baseline) ===")
print(base[cols].round(2).to_string(index=False))

ok = R[(R.n_old >= 60) & (R.n_new >= 40)].sort_values("net_old", ascending=False)
print("\n=== Top 15 by OLDER-days net/trade (min 60 older and 40 newer trades) ===")
print(ok[cols].head(15).round(2).to_string(index=False))

both = ok[(ok.net_old > 0) & (ok.net_new > 0)]
print(f"\n=== Settings positive in BOTH halves: {len(both)} of {len(ok)} ===")
print(both[cols].head(15).round(2).to_string(index=False) if len(both) else "none")
print("\nFull table saved to sweep_results.csv")
print("Net figures are Rs per trade, no daily limits, whole universe (not just the nightly picks).")
