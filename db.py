import os
import sqlite3

TRADE_COLS = ["date", "symbol", "side", "rule_version", "pick_rank", "trigger_time", "entry_time",
              "entry_price", "stop", "target", "qty", "risk_rs", "exit_time", "exit_price", "exit_reason",
              "gross", "charges", "net", "r_mult", "slip_rs", "status", "dq", "features"]


def connect(path="data/log.db"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    for table in ("trades", "shadow"):      # shadow = every trigger on every stock (v2 training data)
        c.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(TRADE_COLS)}, PRIMARY KEY (date, symbol))")
    c.execute("CREATE TABLE IF NOT EXISTS picks "
              "(day, symbol, rank, score, bias, triggered, note, PRIMARY KEY (day, symbol))")
    c.execute("CREATE TABLE IF NOT EXISTS model_log (day, kind, symbol, value, note)")
    c.execute("CREATE TABLE IF NOT EXISTS ledger (effective TEXT, amount REAL, note TEXT, created TEXT)")
    return c


def save_trades(c, trades, table="trades"):
    q = f"INSERT OR REPLACE INTO {table} VALUES ({','.join('?' * len(TRADE_COLS))})"
    c.executemany(q, [[t.get(k) for k in TRADE_COLS] for t in trades])
    c.commit()


def get_trade(c, day, sym):
    return c.execute("SELECT * FROM trades WHERE date=? AND symbol=?", (str(day), sym)).fetchone()


def day_trades(c, day):
    return [dict(r) for r in c.execute("SELECT * FROM trades WHERE date=?", (str(day),))]


def delete_day(c, day):
    c.execute("DELETE FROM trades WHERE date=?", (str(day),))
    c.commit()


def closed_trades(c, version):
    rows = c.execute("SELECT * FROM trades WHERE status='closed' AND rule_version=?", (version,))
    return [dict(r) for r in rows]


def save_picks(c, day, picks):
    c.execute("DELETE FROM picks WHERE day=?", (str(day),))
    c.executemany("INSERT INTO picks (day, symbol, rank, score, bias) VALUES (?,?,?,?,?)",
                  [(str(day), s, i, round(sc, 3), b) for i, (s, sc, b) in enumerate(picks, 1)])
    c.commit()


def picks_for(c, day):
    return [r["symbol"] for r in c.execute("SELECT symbol FROM picks WHERE day=? ORDER BY rank", (str(day),))]


def mark_picks(c, day, trades, notes):
    traded = {t["symbol"] for t in trades}
    for sym, note in notes.items():
        c.execute("UPDATE picks SET triggered=?, note=? WHERE day=? AND symbol=?",
                  (int(sym in traded), note, str(day), sym))
    c.commit()


def log_model(c, day, kind, rows):
    """Replace today's shadow-model output. rows = [(symbol, value, note)]."""
    c.execute("DELETE FROM model_log WHERE day=? AND kind=?", (str(day), kind))
    c.executemany("INSERT INTO model_log VALUES (?,?,?,?,?)", [(str(day), kind, s, v, n) for s, v, n in rows])
    c.commit()


# ---- paper-account ledger: money added to / withdrawn from the account ----
def add_fund(c, effective, amount, note=""):
    c.execute("INSERT INTO ledger VALUES (?,?,?,datetime('now','localtime'))", (str(effective), float(amount), note))
    c.commit()


def funds(c, upto=None):
    """Sum of deposits (+) and withdrawals (-) effective on or before `upto` (all of them if None)."""
    q, args = "SELECT COALESCE(SUM(amount),0) FROM ledger", ()
    if upto is not None:
        q, args = q + " WHERE effective <= ?", (str(upto),)
    return float(c.execute(q, args).fetchone()[0])


def ledger_rows(c):
    return [dict(r) for r in c.execute("SELECT effective, amount, note, created FROM ledger ORDER BY effective, rowid")]


def realized(c, before=None):
    """Net P&L of closed trades dated strictly before `before` (all of them if None)."""
    q, args = "SELECT COALESCE(SUM(net),0) FROM trades WHERE status='closed'", ()
    if before is not None:
        q, args = q + " AND date < ?", (str(before),)
    return float(c.execute(q, args).fetchone()[0])
