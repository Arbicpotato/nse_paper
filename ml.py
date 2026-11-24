"""v2: shadow trades + shadow models. The models only report; they never change live picks or trades."""
import json
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import brier_score_loss, roc_auc_score

import db
import engine
from engine import rsi

MODELS = "data/models"
TFEATS = ["gap", "or_pct", "atr_pct", "relvol", "rsi", "vwap_dist", "nifty_ret", "hour", "side"]
DFEATS = ["rng", "rng_ratio", "avg_rng20", "loc", "gap", "ret1", "ret5", "ret20", "trend", "dist20",
          "rsi", "brk", "volr", "nifty_trend", "nifty_ret1"]


# ---------------------------------------------------------------- shadow trades (all stocks, all days)
def shadow_build(cfg, c, only_day=None):
    """Replay the v1 trigger on every stock and saved day; no picks, no daily limits. Returns count."""
    import data
    nifty, rows = data.load("NIFTY", "5m"), []
    for sym in cfg["universe"]:
        df5, df1 = data.load(sym, "5m"), data.load(sym, "1m")
        if df5.empty:
            continue
        days = [only_day] if only_day else sorted(set(df5.index.date))[3:]
        for day in days:
            tr, _ = engine.simulate_day(df5, day, cfg, nifty, df1)
            if tr and tr["status"] == "closed":
                rows.append({**tr, "symbol": sym})
    if only_day:
        c.execute("DELETE FROM shadow WHERE date=?", (str(only_day),))
    else:
        c.execute("DELETE FROM shadow")
    db.save_trades(c, rows, "shadow")
    return len(rows)


# ---------------------------------------------------------------- trade scorer
def _trade_frame(rows):
    df = pd.DataFrame(rows)
    f = pd.DataFrame(df["features"].map(json.loads).tolist())
    f["side"] = np.where(df["side"] == "LONG", 1, -1)
    return df, f[TFEATS]


def _clf():
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                          min_samples_leaf=20, random_state=0)


def train_trade_scorer(cfg, c):
    rows = [dict(r) for r in c.execute("SELECT * FROM shadow WHERE status='closed'")]
    if len(rows) < 150:
        return print(f"Trade scorer: only {len(rows)} shadow trades, need 150+. Skipped.")
    df, X = _trade_frame(rows)
    y = (df.net > 0).astype(int).values
    cut = sorted(df.date.unique())[int(df.date.nunique() * 0.7)]     # train on earlier dates, test on later
    tr = (df.date < cut).values
    te = ~tr
    if te.sum() < 30 or len(set(y[te])) < 2 or len(set(y[tr])) < 2:
        return print("Trade scorer: not enough variety in the test period. Skipped.")
    m = _clf().fit(X[tr], y[tr])
    p = m.predict_proba(X[te])[:, 1]
    net = df.net.values[te]
    risk, ch = df.risk_rs[tr].mean(), df.charges[tr].mean()
    be = (risk + ch) / (risk * (1 + cfg["target_rr"]))
    keep = p >= be + 0.05
    print(f"\n== Trade scorer (train {tr.sum()} trades before {cut}, test {te.sum()} after) ==")
    print(f"AUC {roc_auc_score(y[te], p):.3f} (0.5 = no skill)   Brier {brier_score_loss(y[te], p):.3f}")
    print(f"test win rate {y[te].mean():.1%}, break-even {be:.1%}")
    print(f"avg net/trade: all {net.mean():.2f}  |  model-kept ({keep.sum()} trades) "
          f"{net[keep].mean() if keep.any() else float('nan'):.2f}")
    cal = pd.DataFrame({"bin": pd.cut(p, [0, .4, .45, .5, .55, .6, 1.0]), "predicted": p, "actual": y[te]})
    print(cal.groupby("bin", observed=True).agg(n=("actual", "size"), predicted=("predicted", "mean"),
                                                actual=("actual", "mean")).round(3).to_string())
    hold = df.symbol.isin(sorted(df.symbol.unique())[::4]).values        # stocks the model never saw
    if hold.sum() >= 30 and (~hold).sum() >= 30 and len(set(y[hold])) == 2:
        mh = _clf().fit(X[~hold], y[~hold])
        print(f"held-out stocks AUC {roc_auc_score(y[hold], mh.predict_proba(X[hold])[:, 1]):.3f}")
    os.makedirs(MODELS, exist_ok=True)
    joblib.dump(_clf().fit(X, y), f"{MODELS}/trade_scorer.joblib")       # final model uses all data


def score_trades(c, day, trades):
    path = f"{MODELS}/trade_scorer.joblib"
    if not trades or not os.path.exists(path):
        return []
    _, X = _trade_frame(trades)
    ps = joblib.load(path).predict_proba(X)[:, 1]
    out = [(t["symbol"], float(p), t["side"]) for t, p in zip(trades, ps)]
    db.log_model(c, day, "trade", out)
    return out


# ---------------------------------------------------------------- picker model (daily bars, whole universe)
def daily_features(df, nd):
    c, h, l, o, v = df.close, df.high, df.low, df.open, df.volume
    rng = (h - l) / c
    avg = rng.rolling(20).mean()
    e20, e50 = c.ewm(span=20).mean(), c.ewm(span=50).mean()
    n20, n50 = nd.close.ewm(span=20).mean(), nd.close.ewm(span=50).mean()
    f = pd.DataFrame({
        "rng": rng, "rng_ratio": rng / avg, "avg_rng20": avg,
        "loc": ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5),
        "gap": o / c.shift() - 1,
        "ret1": c.pct_change(), "ret5": c.pct_change(5), "ret20": c.pct_change(20),
        "trend": e20 / e50 - 1, "dist20": c / e20 - 1, "rsi": rsi(c),
        "brk": ((c > h.shift().rolling(10).max()) | (c < l.shift().rolling(10).min())).astype(float),
        "volr": v / v.rolling(20).mean(),
        "nifty_trend": (n20 / n50 - 1).reindex(df.index, method="ffill"),
        "nifty_ret1": nd.close.pct_change().reindex(df.index, method="ffill"),
        "price": c, "turnover_cr": (c * v).rolling(20).mean() / 1e7,
        "y": rng.shift(-1),                         # label: next day's range as a share of close
    })
    return f.replace([np.inf, -np.inf], np.nan)


def eligible(f, cfg):
    return (f.price <= cfg["capital"]) & (f.turnover_cr >= cfg["min_turnover_cr"]) & (f.avg_rng20 >= cfg["min_daily_range"])


def train_picker(cfg):
    import data
    nd = data.fetch("NIFTY", "1d", "3y")
    parts = []
    for sym in cfg["universe"]:
        d = data.fetch(sym, "1d", "3y")
        if len(d) >= 120 and not nd.empty:
            parts.append(daily_features(d, nd).assign(symbol=sym))
    if not parts:
        return print("Picker model: no daily data. Skipped.")
    allf = pd.concat(parts)
    allf.index.name = "date"
    lab = allf.reset_index().dropna(subset=DFEATS + ["y"])
    dates = sorted(lab.date.unique())
    cut = dates[int(len(dates) * 0.7)]
    tr, te = lab[lab.date < cut], lab[lab.date >= cut]
    reg = lambda: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150,
                                                min_samples_leaf=50, random_state=0)
    m = reg().fit(tr[DFEATS], tr.y)
    te = te[eligible(te, cfg)].copy()
    te["pred"] = m.predict(te[DFEATS])
    k, res = cfg["picks_per_night"], []
    for _, g in te.groupby("date"):
        if len(g) >= k + 3:
            top = g.nlargest(k, "pred")
            res.append((top.y.mean(), g.nlargest(k, "avg_rng20").y.mean(), g.y.mean(),
                        (top.y >= cfg["min_daily_range"]).mean()))
    if not res:
        return print("Picker model: too few eligible stocks per day to test. Skipped.")
    r = np.array(res).mean(axis=0)
    print(f"\n== Picker model (train {len(tr)} stock-days before {str(cut)[:10]}, tested on {len(res)} later days) ==")
    print(f"avg next-day range of picks: model top{k} {r[0]:.2%} | naive 'recently volatile' top{k} {r[1]:.2%} "
          f"| all eligible {r[2]:.2%}")
    print(f"share of model picks with next-day range >= {cfg['min_daily_range']:.1%}: {r[3]:.1%}")
    print("The model is only useful if it beats the naive column by a clear margin.")
    os.makedirs(MODELS, exist_ok=True)
    joblib.dump(reg().fit(lab[DFEATS], lab.y), f"{MODELS}/picker.joblib")


def model_picks(cfg, daily, nd, for_day):
    path = f"{MODELS}/picker.joblib"
    if not os.path.exists(path):
        return None
    rows = [daily_features(d, nd).iloc[[-1]].assign(symbol=s) for s, d in daily.items()
            if len(d) >= 60 and str(for_day) not in cfg["event_blacklist"].get(s, [])]
    if not rows:
        return None
    f = pd.concat(rows).dropna(subset=DFEATS)
    f = f[eligible(f, cfg)].copy()
    if f.empty:
        return None
    f["pred"] = joblib.load(path).predict(f[DFEATS])
    return [(r.symbol, float(r.pred)) for r in f.nlargest(cfg["picks_per_night"], "pred").itertuples()]


# ---------------------------------------------------------------- evening hooks (return message lines)
def after_settle(cfg, c, day, trades):
    lines = [f"Shadow trades logged for {day}: {shadow_build(cfg, c, day)}"]
    lines += [f"  model score {s} {side}: {p:.0%} (shadow only)" for s, p, side in score_trades(c, day, trades)]
    return lines


def picks_line(cfg, c, daily, nd, tomorrow):
    top = model_picks(cfg, daily, nd, tomorrow)
    if top is None:
        return ["Picker model not trained yet (run: main.py train)"]
    db.log_model(c, tomorrow, "pick", [(s, p, "") for s, p in top])
    return ["Model top 5 (shadow, not used): " + ", ".join(f"{s} ({p:.1%})" for s, p in top)]
