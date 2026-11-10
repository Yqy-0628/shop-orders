# -*- coding: utf-8 -*-
"""生成 20 个 SKU × 84 天的仿真流水（含缺货截断）。

订货策略刻意设为「上周同星期销量 × 0.95」——模拟老板怕报损、故意少订。
这正是我们要证明的那个行为。
"""
import csv
import random
import datetime as dt
from pathlib import Path

random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

OPEN_H, CLOSE_H = 9, 21          # 营业 9:00-21:00
HOURS = list(range(OPEN_H, CLOSE_H))   # 9..20 共 12 个时段
WEIGHTS = [0.40, 0.50, 0.60, 0.90, 1.20, 1.50, 1.40, 1.00, 0.90, 0.80, 0.70, 0.60]
WEEKDAY_FACTOR = {0: 0.92, 1: 0.88, 2: 0.96, 3: 1.00, 4: 1.14, 5: 1.30, 6: 1.24}

TEMPLATES = {
    "烘焙": dict(prefix="烘焙", price=12.0, cost=6.0, salvage=2.4, shelf=1, mu=18,
              names=["吐司", "牛角包", "菠萝包", "蛋挞", "贝果"]),
    "鲜食": dict(prefix="鲜食", price=15.0, cost=8.0, salvage=3.0, shelf=1, mu=14,
              names=["三明治", "饭团", "沙拉", "关东煮", "热压卷"]),
    "饮品": dict(prefix="饮品", price=9.0, cost=3.0, salvage=2.4, shelf=1, mu=12, sigma=4.0,
              names=["鲜奶茶", "美式", "柠檬水", "豆浆", "气泡水"]),
    "日配": dict(prefix="日配", price=6.0, cost=3.6, salvage=1.8, shelf=3, mu=32,
              names=["牛奶", "酸奶", "鸡蛋", "面包片", "火腿"]),
}

SKUS = []
for cat, t in TEMPLATES.items():
    for i, nm in enumerate(t["names"], 1):
        mu = t["mu"] * random.uniform(0.85, 1.15)
        SKUS.append(dict(
            sku_id=f"{cat[:2]}{i:02d}",
            name=nm,
            category=cat,
            cost=round(t["cost"] * random.uniform(0.95, 1.05), 2),
            price=round(t["price"] * random.uniform(0.95, 1.05), 2),
            salvage=round(t["salvage"], 2),
            shelf_life_days=t["shelf"],
            mu=round(mu, 1),
            sigma=round(t.get("sigma") or mu * 0.18, 2),
        ))

END = dt.date(2026, 11, 8)
DAYS = [END - dt.timedelta(days=i) for i in range(83, -1, -1)]


def spread_day(total, weights):
    sw = sum(weights)
    out, acc = [], 0
    for w in weights[:-1]:
        q = int(round(total * w / sw))
        out.append(q)
        acc += q
    out.append(max(0, total - acc))
    return out


def main():
    move_rows, sales_rows, stockout_rows = [], [], []
    prev_week_sold = {}          # (sku, weekday) -> 上周同星期销量
    for d in DAYS:
        wd = d.weekday()
        fac = WEEKDAY_FACTOR[wd]
        for s in SKUS:
            demand = max(0, int(round(s["mu"] * fac * random.gauss(1.0, 0.18))))

            # 订货策略：上周同星期卖多少，这周就订多少（老板的“经验法”）
            base = prev_week_sold.get((s["sku_id"], wd))
            if base is None:
                order = max(1, int(round(s["mu"] * fac)))
            else:
                order = max(1, int(round(base * 1.08)))

            move_rows.append([s["sku_id"], d.isoformat(), "入库", order, s["cost"], "已到货"])

            hourly = spread_day(demand, WEIGHTS)
            rem = order
            sold = 0
            stockout_start = None
            for h, want in zip(HOURS, hourly):
                take = min(want, rem)
                if take > 0:
                    sales_rows.append([s["sku_id"], d.isoformat(), h, wd, take, s["price"]])
                sold += take
                rem -= take
                if rem <= 0 and want > 0 and stockout_start is None:
                    stockout_start = h
                    break

            if stockout_start is not None and stockout_start < CLOSE_H - 1:
                stockout_rows.append([s["sku_id"], d.isoformat(), stockout_start, CLOSE_H])

            # 当天卖不完、且保质期只有一天的，记为报损（负数）
            if s["shelf_life_days"] == 1:
                left = max(0, order - sold)
                if left:
                    move_rows.append([s["sku_id"], d.isoformat(), "报损", -left, s["cost"], "已到货"])

            prev_week_sold[(s["sku_id"], wd)] = sold

    def dump(name, header, rows):
        with open(DATA / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        print(f"{name:16s} {len(rows):>6d} 行")

    dump("sku.csv", ["sku_id", "name", "category", "cost", "price",
                     "salvage", "shelf_life_days", "mu", "sigma"],
         [[s["sku_id"], s["name"], s["category"], s["cost"], s["price"],
           s["salvage"], s["shelf_life_days"], s["mu"], s["sigma"]] for s in SKUS])
    dump("stock_move.csv", ["sku_id", "day", "type", "qty", "unit_cost", "status"], move_rows)
    dump("sales.csv", ["sku_id", "day", "hour", "weekday", "qty", "unit_price"], sales_rows)
    dump("stockout.csv", ["sku_id", "day", "start_hour", "end_hour"], stockout_rows)
    print(f"\n覆盖 {DAYS[0]} ~ {DAYS[-1]}，共 {len(DAYS)} 天，{len(SKUS)} 个 SKU")


if __name__ == "__main__":
    main()
