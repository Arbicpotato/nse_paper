"""Local dashboard. Run: python main.py dash  ->  http://127.0.0.1:8765 (auto-refreshes every 30 s)."""
import html
import os
import time
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import db
import report

_px = {}


def last_price(sym):
    """Latest 5-min close for an open position, cached for 60 s. None if unavailable."""
    hit = _px.get(sym)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        import data
        df = data.fetch(sym, "5m", "1d")
        p = float(df.close.iloc[-1]) if len(df) else None
    except Exception:
        p = None
    _px[sym] = (time.time(), p)
    return p


def money(v):
    if v is None:
        return "n/a"
    return f'<span class="{"pos" if v > 0 else "neg" if v < 0 else ""}">{v:+,.2f}</span>'


def table(head, rows):
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>" if rows else "<p class='dim'>Nothing yet.</p>"


def page(cfg):
    c = db.connect()
    today = str(date.today())
    realized_all, funds = db.realized(c), db.funds(c)
    day = db.day_trades(c, today)
    realized_today, unreal, unreal_ok, rows = 0.0, 0.0, True, []
    for t in sorted(day, key=lambda x: x["entry_time"]):
        if t["status"] == "closed":
            realized_today += t["net"] or 0
            rows.append([t["symbol"], t["side"], t["qty"], t["entry_price"], t["stop"], t["target"],
                         f'{t["exit_price"]} ({t["exit_reason"]})', money(t["net"])])
        else:
            px = last_price(t["symbol"])
            side = 1 if t["side"] == "LONG" else -1
            u = None if px is None else side * (px - t["entry_price"]) * t["qty"]
            unreal_ok &= u is not None
            unreal += u or 0
            rows.append([t["symbol"], t["side"], t["qty"], t["entry_price"], t["stop"], t["target"],
                         f"OPEN, now {px}", money(u)])
    balance = cfg["capital"] + funds + realized_all
    hb = "data/heartbeat.txt"
    age = time.time() - os.path.getmtime(hb) if os.path.exists(hb) else None
    health = ("<span class='pos'>live engine running</span>" if age is not None and age < 420 else
              f"live engine idle (last run {datetime.fromtimestamp(os.path.getmtime(hb)):%d %b %H:%M})" if age is not None
              else "live engine has not run yet")
    nxt = c.execute("SELECT MAX(day) FROM picks").fetchone()[0]
    picks = c.execute("SELECT symbol, rank, score, bias FROM picks WHERE day=? ORDER BY rank", (nxt,)).fetchall() if nxt else []
    n = cfg["picks_per_night"]
    prow = [[p["rank"], p["symbol"], "LONG bias" if p["bias"] > 0 else "SHORT bias", f'{p["score"]:.2f}',
             "watching" if p["rank"] <= n else "extra"] for p in picks]
    rep = report.render(report.stats(db.closed_trades(c, cfg["rule_version"]), cfg), cfg)
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>NSE paper trader</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--dim:#777;--line:#ddd;--pos:#0a7d33;--neg:#c0392b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16181c;--fg:#e8e8e8;--dim:#9aa;--line:#333;--pos:#4cd27a;--neg:#ff6b5e}}}}
body{{font-family:system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg);margin:24px;max-width:980px}}
h2{{margin:28px 0 8px;font-size:1.05rem}} .cards{{display:flex;gap:14px;flex-wrap:wrap}}
.card{{border:1px solid var(--line);border-radius:10px;padding:12px 18px;min-width:170px}}
.card b{{display:block;font-size:1.5rem}} .dim{{color:var(--dim)}} .pos{{color:var(--pos)}} .neg{{color:var(--neg)}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}}
pre{{background:transparent;border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto}}
</style></head><body>
<h1>NSE paper trader <span class="dim" style="font-size:.9rem">rule {html.escape(cfg['rule_version'])} - paper money</span></h1>
<p class="dim">{health} - page updated {datetime.now():%d %b %H:%M:%S}</p>
<div class="cards">
<div class="card">Paper balance<b>Rs {balance:,.2f}</b><span class="dim">start {cfg['capital']:,.0f} + added {funds:+,.0f} + closed trades {realized_all:+,.2f}</span></div>
<div class="card">Today, realized<b>{money(realized_today)}</b></div>
<div class="card">Open positions<b>{money(unreal if unreal_ok else None)}</b><span class="dim">before exit costs</span></div>
<div class="card">Today, total<b>{money(realized_today + unreal if unreal_ok else None)}</b></div></div>
<h2>Today's trades ({today})</h2>
{table(["Stock", "Side", "Qty", "Entry", "Stop", "Target", "Exit / now", "Net Rs"], rows)}
<h2>Top picks for {html.escape(str(nxt))}</h2>
{table(["#", "Stock", "Bias", "Score", "Use"], prow)}
<h2>Readiness</h2><pre>{html.escape(rep)}</pre></body></html>"""


def serve(cfg, port=8765):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = page(cfg).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", port), H)
    print(f"Dashboard: http://127.0.0.1:{port}   (Ctrl+C to stop)")
    import webbrowser
    webbrowser.open(f"http://127.0.0.1:{port}")
    srv.serve_forever()
