# -*- coding: utf-8 -*-
"""用真实的 Online Retail 日销量，校准我们仿真里“需求波动”这个假设。

我们仿真用的是：日需求 ~ 均值 × N(1, 0.18)，即变异系数 CV≈0.18。
这里从真实数据算出 CV 到底多大，以及星期几效应。

跑法：python scripts/calibrate_sigma.py
"""
from pathlib import Path

import pandas as pd

SRC = Path(r"C:\Users\姚倩怡\Doubao\chats\2026-11-09\new-chat\online-retail\daily_sku.csv")
OUT = Path(__file__).resolve().parent.parent / "docs"
OUT.mkdir(exist_ok=True)


def main():
    df = pd.read_csv(SRC, parse_dates=["date"])
    df["weekday"] = df["date"].dt.dayofweek
    days = df["date"].nunique()
    print(f"原始：{len(df):,} 行 / {df.StockCode.nunique():,} 个 SKU / {days} 天 "
          f"({df.date.min().date()} ~ {df.date.max().date()})")

    # 补齐零销日：某 SKU 某天没记录 = 那天卖 0
    pivot = df.pivot_table(index="date", columns="StockCode", values="qty",
                           aggfunc="sum").reindex(
        pd.date_range(df.date.min(), df.date.max(), freq="D")).fillna(0)

    stat = pivot.agg(["mean", "std"]).T
    stat["days"] = (pivot > 0).sum()
    stat["cv"] = stat["std"] / stat["mean"].replace(0, pd.NA)

    # 只留有持续销量的：半年以上有成交、日均 3 件以上
    good = stat[(stat["days"] >= 180) & (stat["mean"] >= 3)].dropna()
    print(f"筛出 {len(good)} 个有持续销量的 SKU（≥180 天有成交、日均≥3 件）")
    print()
    print("日销量变异系数 CV 的分布：")
    q = good["cv"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    for k, v in q.items():
        print(f"  {int(k*100):>3d}% 分位   {v:.2f}")
    print(f"  均值           {good['cv'].mean():.2f}")
    print(f"\n我们仿真用的 CV = 0.18")

    # 去星期效应后的 CV
    daily = pivot[good.index]
    tot = daily.sum(axis=1)
    wd_factor = tot.groupby(tot.index.dayofweek).mean() / tot.mean()
    fac = pd.Series(daily.index.dayofweek, index=daily.index).map(wd_factor)
    deseason = daily.div(fac, axis=0)
    cv2 = (deseason.std() / deseason.mean())[good.index]
    print(f"去掉星期几效应后的 CV 中位数 = {cv2.median():.2f}")

    dense = stat[(stat["days"] >= 280) & (stat["mean"] >= 10)].dropna()
    if len(dense):
        print(f"只留最密集的 {len(dense)} 个 SKU（≥280 天有成交、日均≥10）："
              f"CV 中位数 {dense['cv'].median():.2f}")

    print("\n星期几效应（1.00 = 平均）：")
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for i, n in enumerate(names):
        print(f"  {n}  {wd_factor[i]:.2f}")

    print("\n参考：我们仿真里用的星期系数")
    sim = {0: 0.92, 1: 0.88, 2: 0.96, 3: 1.00, 4: 1.14, 5: 1.30, 6: 1.24}
    for i, n in enumerate(names):
        print(f"  {n}  {sim[i]:.2f}")

    good.sort_values("cv").to_csv(OUT / "calibration_cv.csv")


if __name__ == "__main__":
    main()
