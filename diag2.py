import sqlite3, pandas as pd
c = sqlite3.connect("data/log.db")
d = pd.read_sql("select * from shadow where status='closed'", c)
print("avg gross", d.gross.mean(), "| charges", d.charges.mean(), "| slippage", d.slip_rs.mean(), "| net", d.net.mean())
d["hour"] = pd.to_datetime(d.entry_time).dt.hour
print(d.groupby("hour").net.agg(["count", "mean"]))
print(d.groupby(pd.qcut(d.risk_rs, 4)).net.agg(["count", "mean"]))