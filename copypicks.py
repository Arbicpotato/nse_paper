import db
c = db.connect()
c.execute("INSERT OR REPLACE INTO picks (day,symbol,rank,score,bias) SELECT '2026-11-23',symbol,rank,score,bias FROM picks WHERE day='2026-11-24'")
c.commit()
print(db.picks_for(c, "2026-11-23"))
