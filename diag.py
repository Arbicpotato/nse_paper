import sqlite3, pandas as pd
c = sqlite3.connect("data/log.db")
d = pd.read_sql("select * from shadow where status='closed'", c)
print(d.exit_reason.value_counts())
print("ambiguous share:", d.dq.fillna("").str.contains("ambiguous").mean())
print(d.groupby("side").net.agg(["count", "mean"]))
print(d.groupby("exit_reason").net.agg(["count", "mean"]))
