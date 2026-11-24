"""yfinance download + our own saved bar history (Yahoo only keeps ~60 days of 5-min bars)."""
import os

import pandas as pd
import yfinance as yf

IST = "Asia/Kolkata"
COLS = ["open", "high", "low", "close", "volume"]


def ticker(sym):
    return "^NSEI" if sym == "NIFTY" else sym + ".NS"


def fetch(sym, interval, period):
    try:
        df = yf.Ticker(ticker(sym)).history(period=period, interval=interval, auto_adjust=False)
    except Exception as e:
        print(f"fetch failed {sym} {interval}: {e}")
        return pd.DataFrame(columns=COLS)
    if df.empty:
        return pd.DataFrame(columns=COLS)
    df.columns = [c.lower() for c in df.columns]
    df = df[COLS].dropna()
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(IST)
    return df


def _path(sym, interval):
    return f"data/{interval}/{sym}.csv"


def load(sym, interval):
    p = _path(sym, interval)
    if not os.path.exists(p):
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(p, index_col=0)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(IST)
    return df


def save(sym, interval, new):
    """Merge new bars into the saved history; newer download wins on duplicate timestamps."""
    if new.empty:
        return
    os.makedirs(f"data/{interval}", exist_ok=True)
    df = pd.concat([load(sym, interval), new])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_csv(_path(sym, interval))


def quality(df5, day):
    """Flag days with missing bars (a full NSE session has 75 five-minute bars)."""
    d = df5[df5.index.date == day]
    gaps = (d.index.to_series().diff().dropna() > pd.Timedelta(minutes=5)).sum()
    return "" if len(d) >= 72 and gaps == 0 else f"bad_bars:{len(d)}"
