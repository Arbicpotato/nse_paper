import json
import data, db, engine, main

cfg = json.load(open("config.json"))
c = db.connect()
now = main.now_ist()
today = now.date()
picks = db.picks_for(c, today)
dcfg = main.day_cfg(c, today, cfg)
nifty = data.fetch("NIFTY", "5m", "5d")
print(f"Now {now:%H:%M}. Picks: {', '.join(picks) or 'NONE STORED'}\n")
for s in picks:
    df5 = data.fetch(s, "5m", "5d")
    if df5.empty:
        print(f"{s}: NO DATA from Yahoo\n")
        continue
    tr, note = engine.simulate_day(df5, today, dcfg, nifty, None, now)
    d = engine.prep(df5)
    t = d[d.day == today]
    if t.empty:
        print(f"{s}: no bars for today yet\n")
        continue
    r, orb = t.iloc[-1], t.between_time("09:15", "09:25")
    orh, orl = (orb.high.max(), orb.low.min()) if len(orb) else (float("nan"), float("nan"))
    print(f"{s}: {('TRADE ' + tr['side']) if tr else note}")
    print(f"    last bar {t.index[-1]:%H:%M}  close {r.close:.2f} | opening range {orl:.2f}-{orh:.2f} | "
          f"vwap {r.vwap:.2f} | rsi {r.rsi:.0f} | relvol {r.relvol:.2f} | atr {r.atr / r.close:.2%}\n")
print("LONG needs: close > range high, close > vwap, rsi 55-72, relvol >= 1.0, atr >= 0.15%")
print("SHORT needs: close < range low, close < vwap, rsi 28-45, relvol >= 1.0, atr >= 0.15%")
