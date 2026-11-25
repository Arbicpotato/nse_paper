NSE Intraday Paper Trader - Project Log

Add a new entry at the top of "Change log" after every change to the code, config or setup. Format: date, what changed, why, which files, rule version.

Project summary
Goal: free, self-running paper-trading system for NSE intraday stocks (cash segment, no leverage, no real orders).
Source design: "Intraday NSE Paper-Trading Model: Design, Requirements and Plan" (22 Nov 2026).
Daily cycle (IST): live 08:45 (trades 09:20-15:20), evening 15:45 (save bars, settle, statement, pick tomorrow's list, readiness report).
Current rule version: v3 (v1 history stays in the log). Trade count restarts when the version changes.
Current settings (config.json)

Starting capital Rs 10,000 (deposits/withdrawals tracked in the ledger) | risk per trade 1.5% of balance | each trade uses at most balance / max trades | daily loss limit 3% | max 2 trades/day | target 1.5x risk | slippage 0.07%/side | stop 1.0-2.5 x 5-min ATR | cost gate 0.20 of risk | max gap 2% | min relative volume 1.0 | min 5-min ATR 0.15% | last trigger bar 14:25 | square-off bar 15:10 | 10 picks/night | holidays 2026-11-24 and 2026-12-25 | max drawdown limit 15%.

Status (24 Nov 2026)
23 Nov was the first live day (rule v2): 3 SHORT trades, net Rs -2.94 (NHPC stop, IDFCFIRSTB and UNIONBANK time exits).
Ledger: +5,000 top-up and -2,000 withdrawal pending for 24 Nov. 24 Nov is a holiday, so they take effect on the next trading day.
Windows tasks NSE-Live (08:45) and NSE-Evening (15:45) registered; run_live.bat, run_evening.bat, run_train.bat exist.
Rule version is now v3 (merge below). Closed v3 trades so far: 0.
Change log
2026-11-26 - desktop widget behaviour + dashboard price fallback (display only, rule v3 unchanged)
What (widget, python main.py widget): the pin button now locks the widget. While pinned (the default) it sits at the bottom of the window stack, behind all other windows, and cannot be dragged. Unpinned, it floats on top and can be moved. It has no taskbar button or Alt+Tab entry (tool-window style). The widget now runs its own server on a free port instead of 8765, so it can run alongside main.py dash in any order and cannot reuse a stale process left on 8765.
What (dashboard): bars() falls back to the last 5 days and keeps the latest session when today's 5-minute request is empty (before the open or on a holiday), so charts and prices show the last session instead of "n/a". last_price() uses bars(), so open-position marks use that last close in that case.
Why: the widget could not be locked in place, showed in the taskbar, and shared port 8765 with the dashboard. A stale process on that port made every chart and price show "n/a". Before the open Yahoo can also return no bars for today.
New file: widget.bat (start "" pythonw main.py widget) starts the widget with no console window. To start it with Windows, put a shortcut to it in shell:startup. Use pythonw instead of python to hide the console. If port 8765 is stuck: netstat -ano | findstr :8765, then taskkill /PID <pid> /F.
Files: dashboard.py (_WidgetApi, WJS, WCSS, widget(), bars()) and the new widget.bat. No change to engine.py, config.json, the database or the trading rules.
Not tested: edited and syntax-checked outside the project. Not run on Windows or against Yahoo. Check the pin, bottom stacking and taskbar hiding on first run.
To verify: nothing else should import bars() or last_price() from dashboard.py to make decisions (grep -rn "dashboard" *.py). If something does, it could see the last session's prices before the open.
Rule version: v3, unchanged. Forward-test trade count unaffected.
2026-11-25 - dashboard charts (display only, rule v3 unchanged)
What: new "Charts (5-min, today)" section on the dashboard. One tab per stock traded today, then today's watched picks (?s=SYMBOL). Plotly 2.35.2 candlesticks from a CDN, with VWAP, opening-range high/low, dashed entry/stop/target lines and a trigger-bar marker for each trade.
Optional candlestick-pattern labels (doji, hammer, shooting star, bull/bear engulfing); ?p=0 hides them. Labels are display only and are not used by any trading rule.
Bars are cached for 60 s (new bars() helper; last_price() now reuses it), so each refresh fetches only the selected stock.
Why: to see why a trade fired and where price sat against VWAP and the opening range.
Files: dashboard.py only. No change to engine.py, config.json, the database or the trading rules.
Assumptions to verify on first run: data.fetch returns lowercase open/high/low/close/volume; opening range = first or_bars (default 3) five-minute bars, so check this against engine.py; entry_time parses with pandas.
Rule version: v3, unchanged. Forward-test trade count unaffected. Not built: past-day replay from saved bars.
2026-11-24 - merged with your edited project (rule v3, dashboard added)
Your copy of the project had edits not made in this chat (see the next entry). I kept all of them and added v3 on top.
engine.py: your trade_capital sizing kept; added the v3 cost gate, stop_atr_min/stop_atr_max, first_trigger_bar and pre-prepared frames.
report.py: break-even win rate now includes slippage. ml.py: full shadow rebuild clears old shadow rows first.
config.json: your values kept (capital 10000, risk_pct, picks_per_night 10, holidays); added stop_atr_min 1.0, stop_atr_max 2.5, max_cost_to_risk 0.2, first_trigger_bar; rule_version v3 (trade count restarts; your 3 v2 trades stay in the log).
New dashboard.py and main.py dash (http://127.0.0.1:8765, refreshes every 30 s): balance from your ledger, today's realized and open P&L, today's trades, tomorrow's picks, readiness, live-engine health. live loop writes data/heartbeat.txt each good check.
sweep.py (yours): no longer rewrites engine source; it now sets stop_atr_min/max and turns the cost gate off, so it still reproduces the v1 grid. My separate sweep module was not added.
Check on your saved bars, no daily limits, whole universe: v3 rules gave 37 trades, 40.5% wins vs 46.5% break-even, -0.16R per trade, profit factor 0.65. The v1 rules gave 1,389 trades, 36.7% vs 58.7%, -0.44R, profit factor 0.50. v3 loses far less but still has no edge on about 58 days of data.
2026-11-23 - changes found in your copy (made outside this chat, reconstructed from the code)
Paper-account ledger: main.py fund 5000 [note] (negative = withdraw), balance, statement [date]; ledger table in log.db; statements saved to data/statements/ each evening.
Position sizing from the account balance: risk_pct 1.5% per trade, each trade limited to balance / max_trades_per_day (day_cfg, trade_capital in engine.py).
config: capital 10000, picks_per_night 10, holidays added, rule_version v2.
live: status line every minute with prices and live P&L of open trades; new bar check at 5-minute marks.
Helper files: run_live.bat, run_evening.bat, run_train.bat, copypicks.py, diag.py, diag2.py, diag3.py; your own grid sweep (sweep.py) and its sweep_results.csv: every setting was negative per trade; shorts with stop floor 1.0 came closest to break-even.
2026-11-23 - v3 (cost-aware rules + sweep)
Why: with Rs 1,000 capital the quantity is capped by capital, so risk per trade is only a few rupees and charges plus slippage were over half of it. Real break-even win rate was well above the 48% the report showed; observed win rate was 35%.
engine.py: cost gate (skip a trade if charges + slippage > max_cost_to_risk x risk, set to 0.20), configurable stop clamp (stop_atr_min 1.0 and stop_atr_max 2.5; v1 used 0.5 and 2.0), first_trigger_bar option, pre-prepared frames for speed.
report.py: break-even win rate now includes slippage.
ml.py: full shadow rebuild now clears old shadow rows first.
config.json: rule_version v3 (trade count restarts), new keys stop_atr_min, stop_atr_max, max_cost_to_risk, first_trigger_bar.
Changes come from cost arithmetic, not from a parameter search, but they were chosen after seeing v1 results, so only the live forward test counts. Expect far fewer trades.
2026-11-23 - findings from first train run (no code change)
1,377 shadow trades. Trade scorer AUC 0.475 (no skill); model-kept trades did worse than all trades.
Picker model top 5 averaged 3.32% next-day range vs 3.23% for the naive "recently volatile" top 5 (no clear gain).
Diagnostic: 0% ambiguous bars. Exits: stop 767, target 418, time 192. Avg net: stop -6.18, target +5.44. Long -2.28, short -1.20 per trade.
Conclusion: the v1 trigger shows no edge on about 58 days of backtest. Live paper trading stays on v1 (live rules unchanged; v2 is shadow-only).
Known issue: report break-even leaves out slippage (real figure nearer 52%). Fix planned in v3.
Decision: v3 = a sweep analysis command (one change at a time, tested on later dates only). A rule change goes live only as a new rule version after the hold-out test.
2026-11-23 - v2 (shadow learning, report-only)
New ml.py: shadow trades (v1 trigger replayed on every stock and saved day, stored in table shadow), trade scorer (gradient boosting on entry features, time-split test, held-out-stock test, calibration table), picker model (daily bars, 3 years, whole universe, predicts next-day range; compared with a naive baseline).
db.py: new tables shadow and model_log (model scores and model top-5 per day). Existing log.db upgrades automatically.
main.py: new train command (weekly); evening now also logs shadow trades, scores live trades, prints the model's top 5 next to the rule-based picks. ML steps are wrapped so they can never break the evening run.
requirements.txt: added scikit-learn. New selftest_ml.py (synthetic data).
Live picks and trades are unchanged: still rule version v1. Models get a vote only after they beat the plain rules on unseen weeks (would be v3).
2026-11-23
Added this PROJECT_LOG.md.
Scheduled tasks registered (NSE-Live, NSE-Evening). First live window opened and closed because no picks existed for 23 Nov (expected).
Planned: redirect task output to live.log / evening.log so crashes are visible (command given, confirm if applied).
2026-11-22/23 - v1 initial build
engine.py: opening-range-breakout trigger (VWAP, relative volume, RSI, Nifty filter), stop/target/time exit, 1-min resolution of same-bar stop+target, daily limits.
costs.py: Zerodha-style intraday charges (about Rs 83 on a Rs 1 lakh round trip, about Rs 1.07 on Rs 1,000).
picker.py: evening scoring on daily bars with liquidity, volatility, price-cap filters.
data.py / db.py: yfinance download, own saved bar history (data/), SQLite trade and pick log (data/log.db).
report.py: win rate vs break-even, expectancy, 2x slippage stress, profit factor, drawdown, readiness status.
main.py: commands fetch, evening, live, report, backtest. notify.py: Telegram alerts (env vars TG_TOKEN, TG_CHAT).
selftest.py: offline checks for costs, triggers, exits, live look-ahead, day limits.
Known shortcuts / not built yet
Probability simulation (design section 6): needs about 3 months of saved bars; build later in report-only mode.
Models do not yet filter trades or choose picks (shadow only).
Picker model label is a proxy (next-day range), not real trade outcome; 1-min bars exist only for ~7 days so older shadow trades with same-bar stop/target are flagged ambiguous (counted as stops).
GIFT Nifty pre-open check, sector-strength score, automatic results/event calendar (manual event_blacklist).
Hypothetical outcomes for picks that never triggered; only the reason is logged.
Skipped-by-limit trades are not logged as hypothetical trades.
One trade per stock per day.
Universe tickers are unverified guesses; failed downloads are skipped.
Open to-do
[ ] Fill holidays in config.json from the NSE list.
[ ] Apply log-file task change; allow-on-battery setting if laptop.
[ ] Set up Telegram (optional).
[ ] Write down limits and the first review date (about 1 month out).
[ ] Weekly: run main.py train and main.py report, back up the data folder.
[ ] Run main.py train once now; then after about 4 weeks compare model vs rules.