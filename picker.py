"""Evening stock picker on daily bars. Equal-weight score, hard filters first."""
import numpy as np

from engine import rsi


def pick(cfg, daily, nifty_daily, for_day):
    nbias = 1 if nifty_daily.close.ewm(span=20).mean().iloc[-1] > nifty_daily.close.ewm(span=50).mean().iloc[-1] else -1
    out = []
    for sym, df in daily.items():
        if len(df) < 60 or str(for_day) in cfg["event_blacklist"].get(sym, []):
            continue
        last = df.iloc[-1]
        turnover_cr = (df.close * df.volume).tail(20).mean() / 1e7
        rng = ((df.high - df.low) / df.close).tail(20).mean()
        if last.close > cfg["capital"] or turnover_cr < cfg["min_turnover_cr"] or rng < cfg["min_daily_range"]:
            continue
        span = last.high - last.low
        loc = (last.close - last.low) / span if span > 0 else 0.5
        e20, e50 = df.close.ewm(span=20).mean().iloc[-1], df.close.ewm(span=50).mean().iloc[-1]
        bias = 1 if e20 > e50 else -1
        r = rsi(df.close).iloc[-1]
        parts = [
            abs(2 * loc - 1),                                              # close near day high/low
            float(np.clip(1 - (span / last.close) / rng, 0, 1)),           # compression
            float(last.close > df.high.iloc[-11:-1].max() or last.close < df.low.iloc[-11:-1].min()),  # 10-day break
            float(np.clip(last.volume / df.volume.tail(20).mean() / 2, 0, 1)),  # volume vs average
            float((last.close - e20) * bias > 0 and 30 < r < 70),          # trend structure, RSI not extreme
            float(bias == nbias),                                          # Nifty alignment
        ]
        out.append((sym, float(np.mean(parts)), bias))
    # shortcut: no sector-strength term (needs sector index data), add when the log shows the picker matters
    return sorted(out, key=lambda x: -x[1])[: cfg["picks_per_night"]]
