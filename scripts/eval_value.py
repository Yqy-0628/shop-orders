# -*- coding: utf-8 -*-
"""反事实回放：面对同一串真实需求，三种订货方式各要付多少代价。

没有真实门店数据时，这是唯一能算出「钱」的证据：
真值（仿真注入的需求）已知，所以可以回答
「如果按系统建议订，这 84 天会少扔多少、少断多少货」。

策略 A  老板经验法：上周同星期卖多少 × 1.08（数据就是这么生成的）
策略 B  系统建议：补齐后的预测 + 报童分位 Q* = μ̂ + z·σ̂
策略 C  朴素均值：补齐后的预测值，不设安全垫

代价口径：
  报废 = max(0, Q - D) × (cost - salvage)，只对保质期 1 天的单品计
  缺货 = max(0, D - Q) × (price - cost)
  总代价 = 两者之和（元）

跑法：python scripts/eval_value.py
"""
import importlib.util
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import pipeline as P

_spec = importlib.util.spec_from_file_location(
    "mdd", ROOT / "scripts" / "make_demo_data.py")
mdd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mdd)


def rebuild():
    """照 make_demo_data 的循环重算：需求真值、销量、订货量、售罄时刻。"""
    truth, sold_q, order_q, so_hour = {}, {}, {}, {}
    prev = {}
    for d in mdd.DAYS:
        wd = d.weekday()
        fac = mdd.WEEKDAY_FACTOR[wd]
        for s in mdd.SKUS:
            demand = max(
                0, int(round(s["mu"] * fac * mdd.random.gauss(1.0, 0.18))))
            base = prev.get((s["sku_id"], wd))
            order = (max(1, int(round(s["mu"] * fac)))
                     if base is None
                     else max(1, int(round(base * 1.08))))
            hourly = mdd.spread_day(demand, mdd.WEIGHTS)
            rem, sold, start = order, 0, None
            for h, want in zip(mdd.HOURS, hourly):
                take = min(want, rem)
                sold += take
                rem -= take
                if rem <= 0 and want > 0 and start is None:
                    start = h
                    break

            truth[(s["sku_id"], d)] = demand
            sold_q[(s["sku_id"], d)] = sold
            order_q[(s["sku_id"], d)] = order
            so_hour[(s["sku_id"], d)] = (
                start if start is not None else mdd.CLOSE_H)
            prev[(s["sku_id"], wd)] = sold
    return truth, sold_q, order_q, so_hour


def series(sku, sold_q, so_hour):
    rows = [dict(day=d.isoformat(), weekday=d.weekday(),
                 sold=sold_q[(sku, d)], so_hour=so_hour[(sku, d)])
            for d in mdd.DAYS]
    df = pd.DataFrame(rows)
    df["soldout"] = df["so_hour"] < mdd.CLOSE_H
    return df


def hourly_rate(hist):
    clean = hist[~hist["soldout"]]
    if clean.empty:
        return 0.0
    return float(clean["sold"].mean() / P.HORIZON)


def cost_of(q, demand, cost, price, salvage, shelf_life):
    """一笔订货的到期成本。"""
    over = max(0, q - demand)
    short = max(0, demand - q)
    waste = over * (cost - salvage) if shelf_life == 1 else 0.0
    lost = short * (price - cost)
    return waste, lost


def main():
    truth, sold_q, order_q, so_hour = rebuild()
    start = 56
    n = NormalDist()
    rows = []
    acc = {k: dict(waste_units=0, short_units=0, waste_cost=0.0,
                   short_cost=0.0, short_days=0) for k in ("A", "B", "C")}

    for s in mdd.SKUS:
        sku, name = s["sku_id"], s["name"]
        df = series(sku, sold_q, so_hour)
        cost, price, salvage = s["cost"], s["price"], s["salvage"]
        life = s["shelf_life_days"]
        cu, co = price - cost, max(1e-6, cost - salvage)
        ratio = min(0.99, max(0.01, cu / (cu + co)))
        z = n.inv_cdf(ratio)

        per = {k: dict(waste_units=0, short_units=0, waste_cost=0.0,
                       short_cost=0.0, short_days=0) for k in ("A", "B", "C")}

        for i in range(start, len(df)):
            hist = df.iloc[:i].copy()
            wd = int(df.iloc[i]["weekday"])
            day = mdd.DAYS[i]
            d_true = truth[(sku, day)]

            hist_f = P.fill_demand(hist, hourly_rate(hist))
            mu_hat = float(P.forecast(hist_f, wd)["value"])
            sd_hat = float(hist_f["demand"].std() or 0.0)

            q = {
                "A": order_q[(sku, day)],
                "B": max(1, int(round(mu_hat + z * sd_hat))),
                "C": max(1, int(round(mu_hat))),
            }
            for k in ("A", "B", "C"):
                w, l = cost_of(q[k], d_true, cost, price, salvage, life)
                per[k]["waste_cost"] += w
                per[k]["short_cost"] += l
                over_units = max(0, q[k] - d_true)
                short_units = max(0, d_true - q[k])
                if life == 1:
                    per[k]["waste_units"] += over_units
                per[k]["short_units"] += short_units
                if short_units > 0:
                    per[k]["short_days"] += 1

        for k in ("A", "B", "C"):
            for f in ("waste_units", "short_units", "waste_cost",
                      "short_cost", "short_days"):
                acc[k][f] += per[k][f]

        rows.append(dict(
            sku=f"{sku} {name}",
            a_cost=per["A"]["waste_cost"] + per["A"]["short_cost"],
            b_cost=per["B"]["waste_cost"] + per["B"]["short_cost"],
            c_cost=per["C"]["waste_cost"] + per["C"]["short_cost"]))

    table = pd.DataFrame(rows)
    tot = {k: acc[k]["waste_cost"] + acc[k]["short_cost"] for k in "ABC"}

    print("=" * 74)
    print("反事实回放：同样 28 天 × 20 单品，三种订货方式的代价")
    print("=" * 74)
    print(f"{'单品':<16}{'老板实际':>11}{'系统建议':>11}{'朴素均值':>11}"
          f"{'系统省':>10}")
    for _, r in table.iterrows():
        save = (r["a_cost"] - r["b_cost"]) / r["a_cost"] * 100 if r["a_cost"] else 0
        print(f"{r['sku']:<16}{r['a_cost']:>10.0f}{r['b_cost']:>11.0f}"
              f"{r['c_cost']:>11.0f}{save:>9.0f}%")

    print("-" * 74)
    for k, label in (("A", "老板实际"), ("B", "系统建议"), ("C", "朴素均值")):
        print(f"{label}　总代价 ¥{tot[k]:>8.0f}　"
              f"报废 {acc[k]['waste_units']:>4d} 件 / ¥{acc[k]['waste_cost']:.0f}　"
              f"缺货 {acc[k]['short_units']:>4d} 件 / ¥{acc[k]['short_cost']:.0f}　"
              f"缺货 {acc[k]['short_days']:>4d} 天")
    print("-" * 74)
    print(f"系统建议比老板经验法少付 ¥{tot['A'] - tot['B']:.0f}"
          f"（{(1 - tot['B'] / tot['A']) * 100:.0f}%）")
    print(f"报告口径参考：省下的钱 ÷ 老板总代价 = "
          f"{(tot['A'] - tot['B']) / tot['A'] * 100:.1f}%")

    # 落盘给页面用，保证界面与文档同一口径
    days = len(mdd.DAYS) - start
    out = []
    for k, label in (("A", "老板实际"), ("B", "系统建议"), ("C", "朴素均值")):
        out.append({"策略": label, "总代价": round(tot[k], 2),
                    "报废件数": acc[k]["waste_units"],
                    "报废成本": round(acc[k]["waste_cost"], 2),
                    "缺货件数": acc[k]["short_units"],
                    "缺货成本": round(acc[k]["short_cost"], 2),
                    "缺货天数": acc[k]["short_days"],
                    "天数": days, "单品": len(mdd.SKUS)})
    pd.DataFrame(out).to_csv(ROOT / "docs" / "value_eval.csv",
                             index=False, encoding="utf-8-sig")
    print(f"已写入 docs/value_eval.csv（{days} 天 × {len(mdd.SKUS)} 单品）")


if __name__ == "__main__":
    main()
