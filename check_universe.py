"""Ticker check.  Run from C:\nse_paper.
  python check_universe.py            saved data for every stock in config.json (no internet needed)
  python check_universe.py list.txt   download-test every symbol in list.txt (one per line, no .NS) and print the OK ones as JSON
'can pass gate' = the widest stop (stop_atr_max x average 5-min bar range) reaches the stop size the cost gate needs."""
import json
import os
import sys

import pandas as pd

cfg = json.load(open("config.json"))
COST_PCT = 0.0023                                                    # ~2 x 0.07% slippage + small-trade charges, as % of position
NEED = COST_PCT / cfg.get("max_cost_to_risk", 0.2)                   # stop size (% of price) the cost gate needs
MULT = cfg.get("stop_atr_max", 2.5)


def row(sym, df):
    d = df[df.index.date >= sorted(set(df.index.date))[-20]] if len(set(df.index.date)) > 20 else df
    rng = ((d.high - d.low) / d.close).mean()
    return (f"{sym:<12} {len(set(df.index.date)):>3} days  last {df.index[-1]:%Y-%m-%d}  price {df.close.iloc[-1]:>8.2f}  "
            f"5-min range {rng:.2%}  can pass gate: {'yes' if rng * MULT >= NEED else 'no'}")


print(f"Cost gate needs a stop of about {NEED:.2%} of price; widest stop is {MULT}x the 5-min range, so range must be >= {NEED / MULT:.2%}.\n")
if len(sys.argv) > 1:
    import data
    syms = [s.strip().upper().replace(".NS", "") for s in open(sys.argv[1]) if s.strip()]
    ok = []
    for s in dict.fromkeys(syms):
        df = data.fetch(s, "5m", "5d")
        if df.empty:
            print(f"{s:<12} NO DATA (wrong ticker or delisted)")
        else:
            ok.append(s)
            print(row(s, df) + ("   (already in universe)" if s in cfg["universe"] else ""))
    print("\nOK symbols (not yet in universe):\n" + json.dumps([s for s in ok if s not in cfg["universe"]]))
else:
    for s in cfg["universe"]:
        p = f"data/5m/{s}.csv"
        if not os.path.exists(p):
            print(f"{s:<12} NO SAVED FILE")
            continue
        df = pd.read_csv(p, index_col=0)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert("Asia/Kolkata")
        print(row(s, df) if len(df) else f"{s:<12} EMPTY FILE")
