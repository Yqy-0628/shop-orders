# -*- coding: utf-8 -*-
"""在库里的仿真数据上重建「真实需求」，评价界面实际在跑的 pipeline.forecast。

背景：make_demo_data.py 只存了被截断的销量，没有存需求真值。
但生成过程是确定性的（random.seed(42)），所以按同样的循环重算一遍，
就能把每一天每个单品的真实需求还原出来，用来给预测打分。

跑法：python scripts/eval_truth.py
"""
import importlib.util
import sys
from pathlib import Path

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
    """照 make_demo_data 的循环重算，不写文件。返回真值、销量、售罄时刻。"""
    truth, sold_q, so_hour = {}, {}, {}
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
            so_hour[(s["sku_id"], d)] = start if start is not None else mdd.CLOSE_H
            prev[(s["sku_id"], wd)] = sold
    return truth, sold_q, so_hour


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


def backtest(df, truth, sku, mode="fill", start=56):
    """mode: fill = 缺货时长×平均率补齐（界面在跑）；raw = 直接用销量；
    clean = 只用没卖光的日子估基准（core/forecast.py 的做法）。"""
    ys, ps, los, his = [], [], [], []
    for i in range(start, len(df)):
        hist = df.iloc[:i].copy()
        wd = int(df.iloc[i]["weekday"])

        if mode == "fill":
            hist = P.fill_demand(hist, hourly_rate(hist))
            res = P.forecast(hist, wd)
        elif mode == "raw":
            hist["demand"] = hist["sold"]
            res = P.forecast(hist, wd)
        elif mode == "clean":
            good = hist[~hist["soldout"]]
            same = good[good["weekday"] == wd]["sold"].tail(8)
            base = float(same.mean()) if len(same) else float(good["sold"].mean())
            tr = P.trend_ratio(hist["sold"].values)
            res = {"value": round(base * tr), "lo": 0.0, "hi": 0.0}
        else:
            raise ValueError(mode)

        y = truth[(sku, mdd.DAYS[i])]
        if y >= 3:
            ys.append(y)
            ps.append(res["value"])
            los.append(res["lo"])
            his.append(res["hi"])
    return (np.array(ys, float), np.array(ps, float),
            np.array(los, float), np.array(his, float))


def mape(y, p):
    return float(np.mean(np.abs(p - y) / y) * 100)


def bias(y, p):
    return float((p.mean() - y.mean()) / y.mean() * 100)


def main():
    truth, sold_q, so_hour = rebuild()
    print(f"重建 {len(mdd.SKUS)} 个单品 × {len(mdd.DAYS)} 天"
          f"（{mdd.DAYS[0]} ~ {mdd.DAYS[-1]}）")

    rows = []
    acc = {"fill": [[], []], "raw": [[], []], "clean": [[], []]}
    cover_hits, cover_n = 0, 0

    for s in mdd.SKUS:
        sku, name = s["sku_id"], s["name"]
        df = series(sku, sold_q, so_hour)

        y, p, lo, hi = backtest(df, truth, sku, "fill")
        _, p_raw, _, _ = backtest(df, truth, sku, "raw")
        _, p_clean, _, _ = backtest(df, truth, sku, "clean")

        for k, v in (("fill", p), ("raw", p_raw), ("clean", p_clean)):
            acc[k][0].append(y)
            acc[k][1].append(v)

        cover_hits += int(((y >= lo) & (y <= hi)).sum())
        cover_n += len(y)

        rows.append(dict(sku=f"{sku} {name}",
                         m_fill=mape(y, p), m_raw=mape(y, p_raw),
                         m_clean=mape(y, p_clean),
                         b_fill=bias(y, p), b_clean=bias(y, p_clean),
                         cover=float(np.mean((y >= lo) & (y <= hi)) * 100),
                         soldout=int(df["soldout"].sum())))

    Y = np.concatenate(acc["fill"][0])
    Pf = np.concatenate(acc["fill"][1])
    Pr = np.concatenate(acc["raw"][1])
    Pc = np.concatenate(acc["clean"][1])

    table = pd.DataFrame(rows).sort_values("m_fill")

    print()
    print("=" * 76)
    print("滚动回测：逐日推进，预测次日（真值 = 仿真注入的真实需求）")
    print("=" * 76)
    print(f"{'单品':<16}{'平均率补齐':>10}{'用销量':>9}{'只用干净日':>11}"
          f"{'补齐偏差':>9}{'覆盖':>7}{'售罄天':>7}")
    for _, r in table.iterrows():
        print(f"{r['sku']:<16}{r['m_fill']:>9.1f}%{r['m_raw']:>8.1f}%"
              f"{r['m_clean']:>10.1f}%{r['b_fill']:>+8.1f}%"
              f"{r['cover']:>6.0f}%{r['soldout']:>7d}")

    print("-" * 76)
    print(f"{'合计':<16}{mape(Y, Pf):>9.1f}%{mape(Y, Pr):>8.1f}%"
          f"{mape(Y, Pc):>10.1f}%{bias(Y, Pf):>+8.1f}%"
          f"{cover_hits / cover_n * 100:>6.1f}%"
          f"{table['soldout'].sum():>7d}")
    print()
    print(f"样本 {len(Y)}（单品×日，真值≥3）；售罄日占 "
          f"{table['soldout'].sum() / (len(mdd.SKUS) * len(mdd.DAYS)) * 100:.0f}%")
    print(f"偏差：补齐 {bias(Y, Pf):+.1f}%　只用干净日 {bias(Y, Pc):+.1f}%　"
          f"用销量 {bias(Y, Pr):+.1f}%")
    print(f"区间名义 90%，实测 {cover_hits / cover_n * 100:.1f}%")


if __name__ == "__main__":
    main()
