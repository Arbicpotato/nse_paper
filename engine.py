"""Trigger + trade simulation. One code path for live, evening settle and backtest."""
import json

import numpy as np
import pandas as pd

from costs import round_trip

BAR = pd.Timedelta(minutes=5)


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def prep(df):
    """Add day, VWAP (per day), ATR(14), RSI(14), relative volume to 5-min bars."""
    df = df.copy()
    df["day"] = df.index.date
    tp = (df.high + df.low + df.close) / 3
    df["vwap"] = (tp * df.volume).groupby(df["day"]).cumsum() / df.volume.groupby(df["day"]).cumsum()
    pc = df.close.shift()
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(), (df.low - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["rsi"] = rsi(df.close)
    df["relvol"] = df.volume / df.volume.shift().rolling(20).mean()
    return df


def _nifty_ret(nifty, day):
    """Nifty move since today's open, as a function of timestamp."""
    n = nifty[nifty.index.date == day].close if nifty is not None and len(nifty) else None
    if n is None or n.empty:
        return lambda ts: 0.0
    o = n.iloc[0]

    def f(ts):
        v = n.asof(ts)
        return 0.0 if pd.isna(v) else v / o - 1
    return f


def _first_touch(df1, start, side, stop, target):
    """Both stop and target inside one 5-min bar: use 1-min bars. Stop wins if unresolved."""
    if df1 is not None and len(df1):
        for _, m in df1[(df1.index >= start) & (df1.index < start + BAR)].iterrows():
            if (m.low <= stop) if side > 0 else (m.high >= stop):
                return "stop", ""
            if (m.high >= target) if side > 0 else (m.low <= target):
                return "target", ""
    return "stop", "ambiguous_bar"


def simulate_day(df5, day, cfg, nifty=None, df1=None, now=None, prepped=False):
    """Replay one stock on one day. Returns (trade_dict | None, note).
    now=None means the day is complete (evening/backtest); otherwise only bars finished by `now` count."""
    df = df5 if prepped else prep(df5)
    t = df[df["day"] == day]
    if now is not None:
        t = t[t.index <= now]
    done = lambda ts: now is None or ts + BAR <= now
    if len(t) < 4:
        return None, "no data"
    prev = df[df["day"] < day]
    gap = t.open.iloc[0] / prev.close.iloc[-1] - 1 if len(prev) else 0.0
    if abs(gap) > cfg["max_gap"]:
        return None, f"dropped: gap {gap:+.1%}"
    orb = t.between_time("09:15", "09:25")
    if len(orb) < 3 or not done(orb.index[-1]):
        return None, "opening range not ready"
    orh, orl = orb.high.max(), orb.low.min()
    mid = (orh + orl) / 2
    nret = _nifty_ret(nifty, day)
    pos = {ts: i for i, ts in enumerate(t.index)}

    for ts, r in t.between_time(cfg.get("first_trigger_bar", "09:30"), cfg["last_trigger_bar"]).iterrows():
        if not done(ts):
            break
        if r[["atr", "rsi", "relvol", "vwap"]].isna().any():
            continue                                   # indicator warm-up
        if r.atr / r.close < cfg["min_atr_pct"] or r.relvol < cfg["min_relvol"]:
            continue
        n = nret(ts)
        if r.close > orh and r.close > r.vwap and 55 <= r.rsi <= 72 and n > -cfg["nifty_max_move"]:
            side = 1
        elif r.close < orl and r.close < r.vwap and 28 <= r.rsi <= 45 and n < cfg["nifty_max_move"]:
            side = -1
        else:
            continue
        i = pos[ts]
        if i + 1 >= len(t):
            return None, "triggered, waiting for entry bar"
        return _trade(t, i, side, r, orh, orl, mid, gap, n, cfg, df1, now, done)
    return None, "no trigger"


def _trade(t, i, side, r, orh, orl, mid, gap, nret, cfg, df1, now, done):
    slip = cfg["slippage"]
    eb = t.iloc[i + 1]                                  # entry = next bar's open, plus slippage
    entry = eb.open * (1 + side * slip)
    risk = float(np.clip(abs(entry - mid), cfg.get("stop_atr_min", 0.5) * r.atr, cfg.get("stop_atr_max", 2.0) * r.atr))
    stop, target = entry - side * risk, entry + side * cfg["target_rr"] * risk
    qty = min(int(cfg["risk_per_trade"] // risk), int(cfg.get("trade_capital", cfg["capital"]) // entry))
    if qty < 1:
        return None, f"skipped: qty 0 (risk/share {risk:.2f}, price {entry:.2f})"
    cost = round_trip(entry, entry, qty, side) + 2 * slip * entry * qty      # v3 cost gate: charges + slippage
    if cost > cfg.get("max_cost_to_risk", 9) * risk * qty:
        return None, f"skipped: costs {cost / (risk * qty):.0%} of risk"

    sq = pd.Timestamp(cfg["squareoff_bar"]).time()
    base = exit_ts = reason = last = None
    flags, late = [], False
    for ts, b in t.iloc[i + 1:].iterrows():
        if ts.time() > sq:
            late = True
            break
        if not done(ts):
            break
        stop_hit = (b.low <= stop) if side > 0 else (b.high >= stop)
        tgt_hit = (b.high >= target) if side > 0 else (b.low <= target)
        if stop_hit and tgt_hit:
            hit, flag = _first_touch(df1, ts, side, stop, target)
            flags += [flag] if flag else []
        else:
            hit = "stop" if stop_hit else "target" if tgt_hit else None
        if hit == "stop":
            base = min(stop, b.open) if side > 0 else max(stop, b.open)   # gap-through fills at the open
            exit_ts, reason = ts + BAR, "stop"
        elif hit == "target":
            base, exit_ts, reason = target, ts + BAR, "target"
        elif ts.time() >= sq:
            base, exit_ts, reason = b.close, ts + BAR, "time"
        if reason:
            break
        last = b
    if reason is None and last is not None and (late or now is None):
        base, exit_ts, reason = last.close, last.name + BAR, "time"   # square-off bar missing / short day
        flags.append("short_day")

    tr = dict(date=str(r.name.date()), side="LONG" if side > 0 else "SHORT", rule_version=cfg["rule_version"],
              trigger_time=str(r.name), entry_time=str(eb.name), entry_price=round(entry, 2),
              stop=round(stop, 2), target=round(target, 2), qty=qty, risk_rs=round(risk * qty, 2),
              status="closed" if reason else "open", dq=" ".join(flags),
              features=json.dumps(dict(gap=round(gap, 4), or_pct=round((orh - orl) / entry, 4),
                                       atr_pct=round(r.atr / r.close, 4), relvol=round(r.relvol, 2),
                                       rsi=round(r.rsi, 1), vwap_dist=round(r.close / r.vwap - 1, 4),
                                       nifty_ret=round(nret, 4), hour=r.name.hour + r.name.minute / 60)))
    if reason:
        exit_px = base * (1 - side * slip)
        gross = side * (exit_px - entry) * qty
        ch = round_trip(entry, exit_px, qty, side)
        net = gross - ch
        tr.update(exit_time=str(exit_ts), exit_price=round(exit_px, 2), exit_reason=reason,
                  gross=round(gross, 2), charges=ch, net=round(net, 2),
                  r_mult=round(net / tr["risk_rs"], 2), slip_rs=round(slip * (entry + base) * qty, 2))
    return tr, "traded"


def run_day(day, picks, bars5, cfg, nifty=None, bars1=None, now=None, limits=True):
    """All picks for one day, with the daily trade-count and loss limits applied in time order."""
    trades, notes = [], {}
    for rank, sym in enumerate(picks, 1):
        if sym not in bars5 or bars5[sym].empty:
            notes[sym] = "no data"
            continue
        tr, notes[sym] = simulate_day(bars5[sym], day, cfg, nifty, (bars1 or {}).get(sym), now)
        if tr:
            tr.update(symbol=sym, pick_rank=rank)
            trades.append(tr)
    trades.sort(key=lambda x: x["entry_time"])
    if not limits:
        return trades, notes
    kept, loss_cap = [], cfg["capital"] * cfg["daily_loss_pct"]
    for tr in trades:
        realized = sum(k["net"] for k in kept if k["status"] == "closed" and k["exit_time"] <= tr["entry_time"])
        if len(kept) >= cfg["max_trades_per_day"] or realized <= -loss_cap:
            notes[tr["symbol"]] = "skipped: daily limit"
            continue
        kept.append(tr)
    return kept, notes
