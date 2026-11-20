# -*- coding: utf-8 -*-
"""给现有库的 sku 表补 barcode 列并填充短码，不动其它数据。

短码规则与 make_demo_data.py 一致：品类一位 + 单品两位，如 SH203。
"""
import datetime
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(r"D:\dpwenzhang\shop-orders")
DB = ROOT / "data" / "shop.db"
CAT_CODE = {"日配": "SH1", "烘焙": "SH2", "饮品": "SH3", "鲜食": "SH4"}

stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
bak = Path(r"C:\Users\姚倩怡\AppData\Local\Temp") / ("shop-backup-%s.db" % stamp)
shutil.copy2(DB, bak)
print("backup:", bak)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

cols = [r[1] for r in conn.execute("PRAGMA table_info(sku)")]
if "barcode" not in cols:
    conn.execute("ALTER TABLE sku ADD COLUMN barcode TEXT")
    print("added column: barcode")
else:
    print("column exists: barcode")

rows = conn.execute("SELECT sku_id, category, name FROM sku ORDER BY category, sku_id").fetchall()
for r in rows:
    code = CAT_CODE.get(r["category"])
    if not code:
        print("skip (unknown category):", r["sku_id"])
        continue
    digits = "".join(ch for ch in r["sku_id"] if ch.isdigit())
    conn.execute("UPDATE sku SET barcode=? WHERE sku_id=?",
                 (code + digits.zfill(2), r["sku_id"]))

conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sku_barcode ON sku(barcode)")
conn.commit()

print("RESULT")
for r in conn.execute("SELECT sku_id, barcode, name, category, price, shelf_life_days "
                      "FROM sku ORDER BY barcode"):
    print(" ", r["barcode"], r["sku_id"], r["name"], r["category"],
          r["price"], r["shelf_life_days"])

print("total:", conn.execute("SELECT COUNT(*) FROM sku").fetchone()[0])
conn.close()
