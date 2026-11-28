"""Max trades per day: the one place that reads and edits it (used by `main.py maxtrades` and the dashboard).

Changes are refused on a trading day from 08:45 until the evening run has finished (it writes
data/statements/<date>.txt), so the live engine and the evening settle always use the same limit.
The live engine reads config.json once at start, so a change applies from the next live start.
"""
import json
import os
import re
from datetime import time as dtime

import pandas as pd

CONFIG = "config.json"
LOW, HIGH = 1, 10
LOCK_FROM = dtime(8, 45)
STATEMENTS = os.path.join("data", "statements")


def current():
    """max_trades_per_day as written in config.json right now."""
    with open(CONFIG, encoding="utf-8") as f:
        return int(json.load(f)["max_trades_per_day"])


def lock_reason(now=None):
    """Why a change is refused right now, or None if it is allowed.
    On a trading day it is locked from 08:45 until today's statement file exists (the evening run has settled the day)."""
    now = now or pd.Timestamp.now(tz="Asia/Kolkata")
    with open(CONFIG, encoding="utf-8") as f:
        holidays = json.load(f).get("holidays", [])
    d = now.date()
    trading_day = d.weekday() < 5 and str(d) not in holidays
    if trading_day and now.time() >= LOCK_FROM and not os.path.exists(os.path.join(STATEMENTS, f"{d}.txt")):
        return ("Today's trades are not settled yet. Change the limit after the evening run has finished, "
                "so live and the evening settle use the same limit.")
    return None


def set_max_trades(n, now=None):
    """Write a new max_trades_per_day into config.json. Returns (ok, message, old, new)."""
    old = current()
    if type(n) is not int or not LOW <= n <= HIGH:
        return False, f"Refused: max trades per day must be a whole number from {LOW} to {HIGH}.", old, old
    why = lock_reason(now)
    if why:
        return False, why, old, old
    if n == old:
        return False, f"Already {old}. Nothing changed.", old, old
    with open(CONFIG, encoding="utf-8", newline="") as f:
        text = f.read()
    new_text, hits = re.subn(r'("max_trades_per_day"\s*:\s*)\d+', lambda m: f"{m.group(1)}{n}", text)
    if hits != 1:
        return False, "Could not find max_trades_per_day in config.json. Nothing changed.", old, old
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    os.replace(tmp, CONFIG)                                  # atomic: config.json is never half-written
    return True, (f"Max trades per day: {old} -> {n}. Applies from the next live start; restart any running live window. "
                  f"Add a PROJECT_LOG.md entry with today's date."), old, n
