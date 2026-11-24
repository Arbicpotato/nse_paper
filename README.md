# NSE intraday paper trader (phase 1)

Setup: `pip install -r requirements.txt`, set the machine clock to IST, edit `config.json`
(fill `holidays` with NSE holiday dates as "YYYY-MM-DD"; check `universe` tickers still exist).
Optional Telegram alerts: env vars `TG_TOKEN`, `TG_CHAT`.

Commands (run from this folder):
- `python selftest.py`   offline checks (costs, trigger, stop/target, live look-ahead, day limits)
- `python main.py fetch`     download and save 5m/1m bars for the universe
- `python main.py backtest`  raw trigger test on saved bars (no picker)
- `python main.py evening`   save bars, settle today, pick tomorrow's 5, print readiness
- `python main.py live`      watch picks 09:20-15:20, log paper trades, send alerts
- `python main.py report`    readiness report
- `python main.py dash`      local dashboard in the browser (balance, P&L, today's trades, picks)
- `python main.py train`     weekly: rebuild shadow trades, retrain both shadow models, print results
- `python selftest_ml.py`    offline check of the ML code

Cron (IST, Mon-Fri): `45 8 * * 1-5 python main.py live` and `45 15 * * 1-5 python main.py evening`

Shortcuts (not built yet): probability simulation (section 6), GIFT Nifty check, sector-strength score,
results/event calendar (use `event_blacklist` by hand), hypothetical outcome for picks that never triggered,
one trade per stock per day.
