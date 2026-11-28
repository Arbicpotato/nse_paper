"""Add or withdraw paper money: the one place that does it (used by `main.py fund` and the dashboard).

A deposit or withdrawal made before 08:45 on a trading day counts from that day's open; anything later counts from
the next trading day. After a change, the picks for that day are rebuilt from the new balance, but only if they
already exist (if not, the next evening run uses the new balance anyway).
"""
import math
from datetime import time as dtime

import db

CUTOFF = dtime(8, 45)
MAX_AMOUNT = 10_000_000
NOTE_MAX = 80


def _m():
    import main                  # lazy: main imports this module, so import it only when it is needed
    return main


def clean(amount, note):
    """Check the inputs. Returns (amount, note) or raises ValueError with a message for the user."""
    if isinstance(amount, bool):
        raise ValueError("Enter the amount as a number.")
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        raise ValueError("Enter the amount as a number.")
    if not math.isfinite(amt):
        raise ValueError("Enter the amount as a number.")
    amt = round(amt, 2)
    if amt == 0:
        raise ValueError("Enter an amount other than 0.")
    if abs(amt) > MAX_AMOUNT:
        raise ValueError(f"The amount must be at most Rs {MAX_AMOUNT:,}.")
    note = " ".join(str(note or "").split())[:NOTE_MAX]          # one line, no control characters, capped
    return amt, note


def effective_day(cfg, now=None):
    """The trading day a change made now counts from."""
    m = _m()
    now = now or m.now_ist()
    today = now.date()
    return today if m.is_trading_day(today, cfg) and now.time() < CUTOFF else m.next_trading_day(today, cfg)


def add(cfg, amount, note="", now=None):
    """Record a deposit (positive) or withdrawal (negative). Returns (ok, message, effective_day)."""
    try:
        amt, note = clean(amount, note)
    except ValueError as e:
        return False, str(e), None
    m = _m()
    c = db.connect()
    eff = effective_day(cfg, now)
    have = m.equity_at(c, eff, cfg)
    if have + amt < 0:
        return False, f"Refused: the balance would go below zero (balance Rs {have:,.2f}).", eff
    db.add_fund(c, eff, amt, note)
    after = m.day_cfg(c, eff, cfg)
    return True, (f"{'Added' if amt > 0 else 'Withdrew'} Rs {abs(amt):,.2f}, counted from {eff}. "
                  f"Balance then: Rs {after['capital']:,.2f}, risk per trade Rs {after['risk_per_trade']:,.2f}, "
                  f"up to Rs {after['trade_capital']:,.0f} per trade."), eff


def repick(cfg, eff):
    """Rebuild the picks for trading day `eff` from the new balance. Returns a message."""
    m = _m()
    c = db.connect()
    if not c.execute("SELECT 1 FROM picks WHERE day=? LIMIT 1", (str(eff),)).fetchone():
        return "The next picks are not made yet, so the evening run will use the new balance."
    import data, picker
    daily = {s: data.fetch(s, "1d", "1y") for s in cfg["universe"]}
    daily = {s: d for s, d in daily.items() if not d.empty}
    nd = data.fetch("NIFTY", "1d", "1y")
    top = picker.pick(m.day_cfg(c, eff, cfg), daily, nd, eff)        # same call the evening run makes
    c.execute("DELETE FROM picks WHERE day=?", (str(eff),))
    c.commit()
    db.save_picks(c, eff, top)
    if not top:
        return f"No stock passes the filters at this balance, so {eff} has no picks."
    return f"Picks for {eff} rebuilt: " + ", ".join(s for s, _, _ in top) + "."
