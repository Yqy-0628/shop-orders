# -*- coding: utf-8 -*-
"""跑一遍真管道，看数字合不合理。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import connect
from core.pipeline import load_daily, fill_demand, hourly_rate, forecast, tiers

conn = connect()
skus = [dict(r) for r in conn.execute(
    "SELECT sku_id, name, mu FROM sku ORDER BY sku_id")]

print(f"{'SKU':<10}{'品名':<8}{'天数':>5}{'售罄':>5}{'速率':>7}"
      f"{'补齐后日均':>10}{'预测':>7}{'区间':>12}")
print("-" * 74)

picked = skus[:3] + [s for s in skus if s["sku_id"] == "饮品01"][:1]
for s in picked:
    df = load_daily(conn, s["sku_id"])
    if df.empty:
        continue
    rate = hourly_rate(conn, s["sku_id"])
    df = fill_demand(df, rate)
    # 预测「下一个星期几」（用最后一天的下一天）
    last_wd = int(df["weekday"].iloc[-1])
    nxt = (last_wd + 1) % 7
    f = forecast(df, nxt)
    print(f"{s['sku_id']:<10}{s['name']:<8}{len(df):>5}{int(df['soldout'].sum()):>5}"
          f"{rate:>7.2f}{df['demand'].mean():>10.1f}{f['value']:>7}"
          f"{str(f['lo']) + '–' + str(f['hi']):>12}")

print()
print("三档建议（饮品01 鲜奶茶）：")
df = load_daily(conn, "饮品01")
df = fill_demand(df, hourly_rate(conn, "饮品01"))
for t in tiers(df, (int(df["weekday"].iloc[-1]) + 1) % 7):
    print(f"  {t['name']:<6} 订 {t['qty']:>3} 个　"
          f"断货 {t['stockout']*100:>4.0f}%　预计报废 {t['waste']:>4.1f} 个")

print()
print("为什么是这个数：")
for e in forecast(df, (int(df["weekday"].iloc[-1]) + 1) % 7)["explain"]:
    print(f"  {e['label']}：{e['value']}")
