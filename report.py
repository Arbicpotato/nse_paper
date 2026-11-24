import pandas as pd


def stats(trades, cfg):
    if not trades:
        return None
    df = pd.DataFrame(trades).sort_values("exit_time")
    net, n = df.net, len(df)
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()
    eq = pd.concat([pd.Series([0.0]), net.cumsum().reset_index(drop=True)])
    avg_risk, avg_ch = df.risk_rs.mean(), (df.charges + df.slip_rs.fillna(0)).mean()   # charges + slippage
    total = net.sum()
    wk = net.groupby(pd.to_datetime(df.date).dt.strftime("%G-%V")).sum()
    by_sym = net.groupby(df.symbol).sum()
    return dict(
        n=n, win_rate=(net > 0).mean(),
        breakeven=(avg_risk + avg_ch) / (avg_risk * (1 + cfg["target_rr"])),
        total=total, expectancy=net.mean(), expectancy_r=df.r_mult.mean(),
        stress=(net - df.slip_rs.fillna(0)).mean(),
        pf=wins / losses if losses else float("inf"),
        dd=(eq.cummax() - eq).max() / cfg["capital"],
        weeks=len(wk),
        top_week=wk.max() / total if total > 0 else 1.0,
        top_sym=by_sym.max() / total if total > 0 else 1.0,
        flagged=int((df.dq.fillna("") != "").sum()),
    )


def render(s, cfg):
    if s is None:
        return f"{cfg['rule_version']}: no closed trades yet -> NOT READY"
    checks = {
        "100+ closed trades": s["n"] >= 100,
        "expectancy > 0 after charges": s["expectancy"] > 0,
        "still > 0 with 2x slippage": s["stress"] > 0,
        "profit factor > 1.3": s["pf"] > 1.3,
        f"drawdown <= {cfg['max_drawdown_pct']:.0%} of capital": s["dd"] <= cfg["max_drawdown_pct"],
        "profit spread (no week/stock > 50%)": s["top_week"] < 0.5 and s["top_sym"] < 0.5,
        "4+ weeks of data": s["weeks"] >= 4,
    }
    status = "READY" if all(checks.values()) else "PROMISING" if s["expectancy"] > 0 and s["stress"] > 0 else "NOT READY"
    lines = [f"Rule {cfg['rule_version']}: {status}  (trades {s['n']}, net Rs {s['total']:.2f})",
             f"win rate {s['win_rate']:.1%} vs break-even (incl. slippage) {s['breakeven']:.1%}",
             f"expectancy Rs {s['expectancy']:.2f} ({s['expectancy_r']:.2f}R), at 2x slippage Rs {s['stress']:.2f}",
             f"profit factor {s['pf']:.2f}, max drawdown {s['dd']:.1%}, data-quality flagged {s['flagged']}"]
    lines += [f"  {'ok' if v else '--'} {k}" for k, v in checks.items()]
    lines.append("  n/a simulation calibration (phase 2)")
    return "\n".join(lines)
