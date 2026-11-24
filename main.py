"""Usage: python main.py fetch | evening | live | report | backtest | train | dash
       python main.py fund 5000 [note]    add money (negative number = withdraw)
       python main.py balance             balance, deposits, P&L
       python main.py statement [YYYY-MM-DD]   trade-by-trade statement for a day"""
import json
import os
import sys
import time
from datetime import date, time as dtime, timedelta

import pandas as pd

import db
import engine
import notify
import report

IST = "Asia/Kolkata"


def now_ist():
    return pd.Timestamp.now(tz=IST)


def is_trading_day(d, cfg):
    return d.weekday() < 5 and str(d) not in cfg["holidays"]


def next_trading_day(d, cfg):
    d += timedelta(days=1)
    while not is_trading_day(d, cfg):
        d += timedelta(days=1)
    return d


RISK_PCT = 0.015          # risk per trade as a share of account balance (override with "risk_pct" in config.json)


def equity_at(c, day, cfg):
    """Account balance at the start of `day`: starting capital + deposits/withdrawals effective by then
    + P&L of all closed trades before that day. cfg["capital"] is the STARTING capital."""
    return cfg["capital"] + db.funds(c, day) + db.realized(c, day)


def day_cfg(c, day, cfg):
    """Config for one trading day with capital and risk sized from that day's opening balance."""
    eq = max(equity_at(c, day, cfg), 0.0)
    # each trade may use at most balance / max_trades_per_day, so trades open at the same time never exceed the balance
    return {**cfg, "capital": eq, "risk_per_trade": round(eq * cfg.get("risk_pct", RISK_PCT), 2),
            "trade_capital": eq / cfg["max_trades_per_day"]}


def _px(x):
    return "-" if x is None else f"{x:.2f}"


def statement(c, cfg, day):
    """End-of-day statement: every trade with its P&L, then the balance."""
    trades = sorted(db.day_trades(c, day), key=lambda t: t["entry_time"] or "")
    opening = equity_at(c, day, cfg)
    added = sum(r["amount"] for r in db.ledger_rows(c) if r["effective"] == str(day))
    lines = [f"===== Daily statement {day} =====",
             f"Opening balance: Rs {opening:,.2f}" + (f"  (includes Rs {added:+,.2f} added/withdrawn today)" if added else "")]
    if not trades:
        lines.append("No trades today.")
    for i, t in enumerate(trades, 1):
        flag = "" if t["status"] == "closed" else "  [OPEN - not settled]"
        lines.append(f"{i}. {t['side']:<5} {t['symbol']:<11} qty {t['qty']:>4}  in {_px(t['entry_price'])} -> out {_px(t['exit_price'])} "
                     f"({t['exit_reason'] or '-'})  gross {t['gross'] or 0:+.2f}  charges {t['charges'] or 0:.2f}  "
                     f"NET {t['net'] or 0:+.2f}{flag}")
    day_net = sum(t["net"] or 0 for t in trades if t["status"] == "closed")
    closing = opening + day_net
    nxt = next_trading_day(day, cfg)
    lines += [f"Day P&L: Rs {day_net:+,.2f} ({len(trades)} trades)",
              f"Closing balance: Rs {closing:,.2f}"]
    pend = [r for r in db.ledger_rows(c) if str(day) < r["effective"] <= str(nxt)]
    if pend:
        lines.append("Pending funds for next trading day: " + ", ".join(f"Rs {r['amount']:+,.2f}" for r in pend))
    return "\n".join(lines)


def fund(cfg):
    args = sys.argv[2:]
    if not args:
        return print("Usage: python main.py fund 5000 [note]   (negative amount = withdraw)")
    amt, note = float(args[0]), " ".join(args[1:])
    c, now = db.connect(), now_ist()
    today = now.date()
    eff = today if is_trading_day(today, cfg) and now.time() < dtime(8, 45) else next_trading_day(today, cfg)
    if equity_at(c, eff, cfg) + amt < 0:
        return print(f"Refused: balance would go below zero (balance Rs {equity_at(c, eff, cfg):,.2f}).")
    db.add_fund(c, eff, amt, note)
    after = day_cfg(c, eff, cfg)
    print(f"{'Added' if amt > 0 else 'Withdrew'} Rs {abs(amt):,.2f}. Effective from trading day {eff} (before that day's open).")
    print(f"Balance at the start of {eff}: Rs {after['capital']:,.2f}, risk per trade Rs {after['risk_per_trade']:,.2f}")


def balance(cfg):
    c = db.connect()
    rows, pnl, today = db.ledger_rows(c), db.realized(c), now_ist().date()
    dep = sum(r["amount"] for r in rows if r["amount"] > 0)
    wd = -sum(r["amount"] for r in rows if r["amount"] < 0)
    print(f"Starting capital     Rs {cfg['capital']:>12,.2f}")
    print(f"Deposits             Rs {dep:>12,.2f}")
    print(f"Withdrawals          Rs {wd:>12,.2f}")
    print(f"Trading P&L (closed) Rs {pnl:>12,.2f}")
    print(f"Balance now          Rs {cfg['capital'] + dep - wd + pnl:>12,.2f}")
    for r in rows:
        print(f"  {r['effective']}  {r['amount']:+,.2f}  {r['note'] or ''}" + ("  (pending)" if r["effective"] > str(today) else ""))


def show_statement(cfg):
    day = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else now_ist().date()
    print(statement(db.connect(), cfg, day))


def readiness(c, cfg):
    return report.render(report.stats(db.closed_trades(c, cfg["rule_version"]), cfg), cfg)


def tick(c, picks, cfg, today, now):
    import data
    bars = {s: data.fetch(s, "5m", "5d") for s in picks}
    if all(df.empty for df in bars.values()):
        raise RuntimeError("no intraday data from Yahoo")
    trades, _ = engine.run_day(today, picks, bars, cfg, data.fetch("NIFTY", "5m", "5d"), None, now)
    for tr in trades:
        old = db.get_trade(c, today, tr["symbol"])
        if old is None:
            notify.send(f"{tr['side']} {tr['symbol']} qty {tr['qty']} entry {tr['entry_price']} "
                        f"stop {tr['stop']} target {tr['target']} (paper)")
        if tr["status"] == "closed" and (old is None or old["status"] == "open"):
            notify.send(f"EXIT {tr['symbol']} {tr['exit_reason']} @ {tr['exit_price']}  net Rs {tr['net']}")
    db.save_trades(c, trades)
    return bars


def show(c, bars, today, now, tag):
    """One status block: trade counts, latest price of every pick, and live P&L of open trades."""
    dt_ = db.day_trades(c, today)
    n_open = sum(1 for t in dt_ if t["status"] != "closed")
    net = sum(t["net"] or 0 for t in dt_ if t["status"] == "closed")
    last = {}
    for s, df in bars.items():
        d = df[df.index.date == today] if len(df) else df
        if len(d):
            last[s] = float(d.close.iloc[-1])
    print(f"{now:%H:%M} {tag} | {n_open} open, {len(dt_) - n_open} closed, net so far Rs {net:+.2f}")
    print("  prices: " + "  ".join(f"{s} {p:.2f}" for s, p in last.items()), flush=True)
    for t in dt_:
        if t["status"] != "closed" and t["symbol"] in last:
            side = 1 if t["side"] == "LONG" else -1
            pnl = side * (last[t["symbol"]] - t["entry_price"]) * t["qty"]
            print(f"  OPEN {t['side']} {t['symbol']} qty {t['qty']}  entry {t['entry_price']:.2f}  now {last[t['symbol']]:.2f}  "
                  f"P&L {pnl:+.2f} (before charges)  stop {t['stop']:.2f}  target {t['target']:.2f}", flush=True)


def live(cfg):
    today = now_ist().date()
    if not is_trading_day(today, cfg):
        return notify.send("Not a trading day, skipping.")
    c = db.connect()
    picks = db.picks_for(c, today)
    if not picks:
        return notify.send("No picks stored for today. Did the evening run happen?")
    dcfg = day_cfg(c, today, cfg)
    notify.send(f"Watching today: {', '.join(picks)}  (capital Rs {dcfg['capital']:,.0f}, risk/trade Rs {dcfg['risk_per_trade']:,.0f})")
    failing, last_slot = False, None
    while now_ist().time() < dtime(15, 20):
        now = now_ist()
        if now.time() >= dtime(9, 20):
            slot = (now.hour, now.minute // 5)
            due = slot != last_slot and (now.minute % 5 > 0 or now.second >= 15)   # new 5-min bar has had 15 s to appear
            try:
                if due:
                    bars = tick(c, picks, dcfg, today, now)
                    last_slot = slot
                    show(c, bars, today, now, "checked")
                else:                                                                # between bars: prices only
                    import data
                    show(c, {s: data.fetch(s, "5m", "1d") for s in picks}, today, now, "prices ")
                failing = False
                open("data/heartbeat.txt", "w").write(str(now))      # dashboard health check
            except Exception as e:
                if not failing:                          # one alert per failure streak
                    notify.send(f"ALERT live tick failed: {e}")
                failing = True
        time.sleep((16 - now_ist().second) % 60 or 60)    # wake at :16 past every minute
    day = db.day_trades(c, today)
    notify.send(f"Live done: {len(day)} trades, net Rs {sum(t['net'] or 0 for t in day):.2f}. Evening run will settle.")


def fetch_all(cfg):
    import data
    for sym in cfg["universe"] + ["NIFTY"]:
        for interval, period in (("5m", "60d"), ("1m", "7d")):
            data.save(sym, interval, data.fetch(sym, interval, period))


def _safe(msg, fn):
    """Shadow-model steps must never break the evening run."""
    try:
        msg += fn()
    except Exception as e:
        msg.append(f"ML step skipped: {e}")


def evening(cfg):
    import data, ml, picker
    today, c = now_ist().date(), db.connect()
    fetch_all(cfg)
    msg = []
    picks = db.picks_for(c, today)
    if is_trading_day(today, cfg) and picks:
        bars5 = {s: data.load(s, "5m") for s in picks}
        bars1 = {s: data.load(s, "1m") for s in picks}
        trades, notes = engine.run_day(today, picks, bars5, day_cfg(c, today, cfg), data.load("NIFTY", "5m"), bars1)
        for tr in trades:
            tr["dq"] = (tr["dq"] + " " + data.quality(bars5[tr["symbol"]], today)).strip()
        db.delete_day(c, today)                          # evening data replaces the live-mode log
        db.save_trades(c, trades)
        db.mark_picks(c, today, trades, notes)
        msg.append(f"Today: {len(trades)} trades, net Rs {sum(t['net'] or 0 for t in trades):.2f}")
        msg += [f"  {s}: {n}" for s, n in notes.items() if n != "traded"]
        _safe(msg, lambda: ml.after_settle(cfg, c, today, trades))
    if is_trading_day(today, cfg):
        stmt = statement(c, cfg, today)
        os.makedirs("data/statements", exist_ok=True)
        open(f"data/statements/{today}.txt", "w", encoding="utf-8").write(stmt + "\n")
        msg.append(stmt)
    daily = {s: data.fetch(s, "1d", "1y") for s in cfg["universe"]}
    daily = {s: d for s, d in daily.items() if not d.empty}
    nd = data.fetch("NIFTY", "1d", "1y")
    tomorrow = next_trading_day(today, cfg)
    top = picker.pick(day_cfg(c, tomorrow, cfg), daily, nd, tomorrow)
    db.save_picks(c, tomorrow, top)
    msg.append(f"Picks for {tomorrow}: " + ", ".join(f"{s} ({'L' if b > 0 else 'S'} {sc:.2f})" for s, sc, b in top))
    _safe(msg, lambda: ml.picks_line(cfg, c, daily, nd, tomorrow))
    msg.append(readiness(c, cfg))
    notify.send("\n".join(msg))


def train(cfg):
    """Weekly: rebuild shadow trades on all saved bars, retrain both shadow models, print how they did."""
    import ml
    c = db.connect()
    print(f"Shadow trades rebuilt: {ml.shadow_build(cfg, c)}")
    ml.train_trade_scorer(cfg, c)
    ml.train_picker(cfg)


def backtest(cfg):
    """Raw trigger test on saved bars: every stock, every saved day, no picker, no daily limits."""
    import data
    nifty, trades = data.load("NIFTY", "5m"), []
    for sym in cfg["universe"]:
        df5, df1 = data.load(sym, "5m"), data.load(sym, "1m")
        if df5.empty:
            continue
        for day in sorted(set(df5.index.date))[3:]:
            tr, _ = engine.simulate_day(df5, day, cfg, nifty, df1)
            if tr and tr["status"] == "closed":
                trades.append({**tr, "symbol": sym})
    print(report.render(report.stats(trades, cfg), cfg))


if __name__ == "__main__":
    cfg = json.load(open("config.json"))
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"fetch": fetch_all, "train": train, "evening": evening, "live": live, "backtest": backtest,
     "dash": lambda cfg: __import__("dashboard").serve(cfg), "fund": fund, "balance": balance, "statement": show_statement,
     "report": lambda cfg: print(readiness(db.connect(), cfg))}.get(cmd, lambda cfg: print(__doc__))(cfg)
