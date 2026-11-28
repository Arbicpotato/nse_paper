NSE Intraday Paper Trader - Project Log

Add a new entry at the top of "Change log" after every change to the code, config or setup. Format: date, what changed, why, which files, rule version.

Project summary
Goal: free, self-running paper-trading system for NSE intraday stocks (cash segment, no leverage, no real orders).
Source design: "Intraday NSE Paper-Trading Model: Design, Requirements and Plan" (22 Nov 2026).
Daily cycle (IST): live 08:45 (trades 09:20-15:20), evening 19:00 (save bars, settle, statement, pick tomorrow's list, readiness report).
Current rule version: v4 (v1 history stays in the log). Trade count restarts when the version changes.
Current settings (config.json)

Starting capital Rs 10,000 (deposits/withdrawals tracked in the ledger) | risk per trade 1.5% of balance | each trade uses at most balance / max trades | daily loss limit 3% | max 2 trades/day (change with main.py maxtrades N) | target 1.5x risk | slippage 0.07%/side | stop 1.0-2.5 x 5-min ATR | cost gate 0.20 of risk | max gap 2% | min relative volume 1.0 | min 5-min ATR 0.15% | last trigger bar 14:25 | square-off bar 15:10 | 10 picks/night | holidays 2026-11-24 and 2026-12-25 | max drawdown limit 15% | retry after skipped trigger: on.

Status (24 Nov 2026)
23 Nov was the first live day (rule v2): 3 SHORT trades, net Rs -2.94 (NHPC stop, IDFCFIRSTB and UNIONBANK time exits).
Ledger: +5,000 top-up and -2,000 withdrawal pending for 24 Nov. 24 Nov is a holiday, so they take effect on the next trading day.
Windows tasks NSE-Live (08:45) and NSE-Evening (19:00) registered; run_live.bat, run_evening.bat, run_train.bat exist.
Rule version is now v4 (retry after skipped trigger). Closed v4 trades so far: 0.
ML status (28 Nov): trade-scorer AUC 0.469 (no skill), picker no better than the naive list. ML gate OFF: live trading uses the rules only. Gate state is on the dashboard (Strategy in use) and in data/ml_gate.json.
Change log
2026-11-28 - ML gate (report only) + 'Strategy in use' dashboard card + check_universe.py (no trading rule change)
What: (1) ml.py: the trade-scorer report now prints break-even with slippage next to the old charges-only figure, and the test trades by exit reason (stop / target / time, average net, share counted as 'wins'). New report-only gate (update_gate): each `train` records the AUC, a bootstrap lower bound of the AUC, test trade count and the reasons it would stay off, in data/ml_gate.json (a rerun on the same day counts once). Gate turns ON only after 3 passing trains spread over 10+ days (AUC lower bound >= 0.55, >= 300 test trades, >= 30 model-kept trades, kept trades beat all trades after costs); turns OFF again if AUC < 0.5 or kept trades stop beating all trades. Nothing in live trading reads the gate. (2) dashboard.py: new 'Strategy in use' card above Readiness: 'Live trading uses: RULES v4', gate ON/OFF (report only), latest trade-scorer AUC with lower bound and test trade count, last 6 trains, and why the gate is off. Reads data/ml_gate.json; shows 'No ML train result yet' until `train` has run with the new ml.py. (3) check_universe.py (new): `python check_universe.py` lists saved bars, last date, price and average 5-min range for every stock in config.json and whether it can pass the cost gate; `python check_universe.py list.txt` download-tests tickers (no .NS) and prints the working ones as JSON for config.json.
Why: train run of 28 Nov: 428 shadow trades; trade scorer (292 train / 136 test) AUC 0.469, Brier 0.295, held-out stocks AUC 0.444; model-kept trades (71) averaged -14.47 vs -5.86 for all; calibration backwards at the top bin (predicted 70%, actual 43%). Picker model top 10 averaged a 4.26% next-day range vs 4.20% for the naive top 10 (all eligible 2.92%): no gain. Conclusion: no model skill, rules stay in charge, models stay shadow. The test win rate (47.1%) looked above break-even (42.9%) while average net was negative: ml.py's break-even left out slippage (report.py already includes it) and 'wins' include time exits with a tiny positive net. Cost gate: cost is about 0.23% of the position (2 x 0.07% slippage + small-trade charges), so at max_cost_to_risk 0.20 the stop must be about 1.15% of price, i.e. 5-min range of about 0.46% or more at the widest 2.5x stop. Low-volatility large caps (ITC, ATR about 0.15%) rarely pass, so widening the universe should favour volatile stocks; wrong tickers also drop out silently (data.fetch returns an empty frame), which check_universe.py shows.
Files: ml.py, dashboard.py, check_universe.py (new), README.md, requirements.txt (joblib listed explicitly), PROJECT_LOG.md. No change to engine.py, config.json, db.py, report.py, data.py or the trading rules.
Not run against your data: gate and card tested on synthetic shadow trades with stand-in db/engine modules, page JavaScript syntax-checked; the download mode of check_universe.py needs internet and was not run.
Rule version: unchanged (v4).
2026-11-26 - chart indicator panels + watchlist follows the newest picks (display only, rule v4 unchanged)
What: (1) under each chart, toggle-able panels for the engine's own filters: RSI 14 (long band 55-72, short 28-45 shaded), ATR % (engine min line from min_atr_pct) and relative volume (min line from min_relvol; bars turn green at or above it). Buttons RSI / ATR / Rel vol in the chart header, choice remembered in the browser; hover tooltip shows the values. Values come from engine.prep() on 5 days of bars, so they match what the live engine sees. (2) Once the evening run has saved picks for a later day, the watchlist tabs, charts and widget list show those picks instead of today's old ones, so they match the 'Top picks' card; before that they behave as before. The chart sub-title says which day the picks are for.
Why: to see why a stock did or did not trigger, and to stop the watchlist showing yesterday's stocks after the evening pick.
Files: dashboard.py only (bars, bars_payload, payload, chart JS, header buttons). No change to engine.py, config.json, the database or the trading rules.
Not run against Yahoo or your database: tested with stand-in db/data/costs modules and headless Chromium.
Rule version: unchanged.
2026-11-26 - dashboard 'Account funds' card + funds.py (no change to trading rules)
What: new funds.py holds the add/withdraw logic (input checks, effective day, refusal if the balance would go below zero) and `python main.py fund` now uses it. Dashboard has an 'Account funds' card: amount, optional note, Add money / Withdraw buttons (POST /fund, local page only) and a list of all deposits and withdrawals with pending ones marked. After a change the picks for the day it takes effect are rebuilt with the same picker call the evening run makes, using that day's new balance (only if those picks already exist; otherwise the next evening run uses it).
Why: change the balance from the dashboard, keep a visible transaction record, and make the next top picks follow the balance without waiting for the next evening run.
Files: funds.py (new), main.py (fund command), dashboard.py (card, /fund endpoint, ledger in the page data), README.md, PROJECT_LOG.md. No change to engine.py, config.json, the database layout or the trading rules.
Not tested on your data: syntax-checked, input checks and effective-day logic run with stand-ins for db/costs/notify/report (those files were not in the zip). The rebuild of picks calls picker.pick and db.save_picks, which I could not see; whether picks actually change with the balance depends on how picker.py uses capital / trade_capital.
Rule version: unchanged.
2026-11-26 - schedule corrected to 19:00 and max-trades lock follows the evening run (no rule change)
What: schtasks shows NSE-Evening runs at 19:00 (next run 26 Nov 7:00 PM) and NSE-Live at 08:45, both weekly. The log said evening 15:45, so the daily-cycle and task lines are corrected to 19:00. The max-trades lock in limits.py was 08:45-15:45, which would have left a gap between 15:45 and 19:00 where a change could reach the evening settle but not live. It is now locked from 08:45 until data/statements/<date>.txt exists (the evening run has settled the day).
Why: live and the evening settle must use the same max_trades_per_day on any given day.
Files: limits.py, README.md, PROJECT_LOG.md. No change to engine.py, config.json, the database or the trading rules.
If the evening run does not run one day the lock stays until midnight; edit config.json by hand if you must.
Rule version: unchanged.
2026-11-26 - compare_retry.py + engine_v4.py (read-only test helpers, nothing live changed)
What: compare_retry.py replays today's picks on today's 5-minute bars with the real engine rules, once as v3 (current engine.py, retry off) and once as v4 (engine_v4.py, retry on), and prints both side by side. It writes nothing to the database or config. engine_v4.py is a test copy of the v4 engine.py.
Why: to see whether v4 would have taken a trade today without touching the live files before tonight's evening run.
Files: new compare_retry.py and engine_v4.py. Delete engine_v4.py once v4 is applied to engine.py. No change to engine.py, config.json, the database or the trading rules.
Not tested on your data: syntax-checked outside the project only.
Rule version: unchanged (v3 live today; v4 files are not applied yet).
2026-11-26 - max trades per day can be changed on the dashboard (rule v4 unchanged)
What: new "Max trades per day" card on the dashboard (right column, under Engine): a - / + stepper and an Apply button. Apply sends POST /maxtrades, which edits max_trades_per_day in config.json. The card shows the capital each trade may use at the chosen limit (balance / limit). New file limits.py holds the shared rules, and python main.py maxtrades now calls it too, so the dashboard and the command behave the same: range 1-10, refused on a trading day from 08:45 until the evening run has finished (the card is greyed out and shows why), applies from the next live start (restart any running live window).
Why: the limit could only be changed from the command line.
Safety: only the dashboard page can call POST /maxtrades (custom header, local Host and Origin required). config.json is written to a temp file and swapped in, so it is never half-written. Only the max_trades_per_day number is edited; the rest of config.json is untouched.
Value now: 2 (unchanged). Every time you change it, add a dated log entry, so forward-test results can be split by limit.
Files: dashboard.py (import limits, _max_info, do_POST, card HTML/CSS/JS), main.py (maxtrades now uses limits), new limits.py, README.md. No change to engine.py, config.json, the database or the trading rules.
Tested outside the project with stub db/report modules: limit changes, range and time-window refusals, and the POST checks. Not run against your real database or in a browser, so check the card on first open.
Rule version: v4, unchanged. Forward-test trade count not restarted.
2026-11-26 - main.py maxtrades command (max trades per day now changeable, rule v4 unchanged)
What: new command python main.py maxtrades [N]. With no number it shows the current limit; with N (1-10) it edits max_trades_per_day in config.json. It is refused on a trading day from 08:45 until the evening run has finished, so live and the evening settle always use the same limit. The live engine reads config.json once at start, so a change applies from the next live start (restart any running live window).
Why: the limit was a fixed value in config.json that had to be edited by hand.
Side effect: each trade may use at most balance / max_trades_per_day, so raising the limit shrinks the capital per trade (and the quantity), and lowering it enlarges them. Risk per trade (1.5% of balance) and the daily loss limit (3%) are unchanged.
Value now: 2 (unchanged). Every time you change it, add a dated log entry, so forward-test results can be split by limit.
Files: main.py (maxtrades, import re, dispatch, docstring), README.md. No change to engine.py, config.json, the database or the trading rules.
Not tested: edited and syntax-checked outside the project. Try python main.py maxtrades first (shows the value, changes nothing).
Rule version: v4, unchanged. Forward-test trade count not restarted.
2026-11-26 - v4: retry after a skipped trigger (rule change, forward-test count restarts)
What: engine.py simulate_day keeps scanning for a later trigger when a trigger is skipped by the cost gate or qty 0, instead of ending that stock's day. Controlled by config key retry_after_skip (true in v4; false reproduces v3). Still one trade per stock per day.
Why: in v3 one rejected early trigger blocked the whole day for that stock, even though a later, cheaper setup could pass the same gate. On the 58 saved days (backtest, no daily limits): v3 44 trades, profit factor 0.70; retry 74 trades, 50% wins, profit factor 1.01, better in both the older and newer halves.
Caveat: profit factor 1.01 is break-even, not an edge, and 74 trades is a small sample. It was chosen after seeing v3 results, so only the live forward test counts. At 2x slippage v3 gives 4 trades at about -51 per trade and retry gives 11 trades at about -49, so both fail the stress test.
Files: engine.py, config.json (rule_version v4, retry_after_skip). No change to costs, the database schema or picks.
Side effect: the next main.py train rebuilds the shadow trades under v4, so AUC before and after is not comparable.
Rule version: v4. Closed v4 trades so far: 0. v3 had 0 closed trades, so nothing is lost.
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
ML gate is report only: nothing in live trading reads data/ml_gate.json.
