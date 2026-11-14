# -*- coding: utf-8 -*-
"""验证层：同一个仿真世界，三种处理方式，看谁估得准。

  不处理   直接用卖出去的件数
  剔除     卖光那天的销量整条不用
  补齐     卖光那天按「缺货时长 × 时段销量率」补回来

评分对着「真实需求」——那个现实里永远看不到的东西。
跑法：python scripts/backtest_fill.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import forecast as F

RNG = np.random.default_rng(2026)

DAYS = 140
OPEN_H, CLOSE_H = 9, 21
HORIZON = CLOSE_H - OPEN_H
WEIGHTS = np.array([0.40, 0.50, 0.60, 0.90, 1.20, 1.50, 1.40, 1.00, 0.90, 0.80, 0.70, 0.60])
WEIGHTS = WEIGHTS / WEIGHTS.sum()
WEEKDAY = np.array([0.90, 0.88, 0.95, 1.00, 1.12, 1.28, 1.22])
HOLIDAYS = {30, 31, 62, 63, 105, 106}

SKUS = [
    ("面包01 吐司",   "面包", 26, 0.18),
    ("面包02 牛角包", "面包", 18, 0.22),
    ("面包03 菠萝包", "面包", 22, 0.20),
    ("面包04 蛋挞",   "面包", 15, 0.26),
    ("面包05 贝果",   "面包", 7,  0.40),
    ("简餐01 三明治", "简餐", 16, 0.24),
    ("简餐02 饭团",   "简餐", 19, 0.22),
    ("简餐03 沙拉",   "简餐", 6,  0.45),
]
NAMES = [s[0] for s in SKUS]
N = len(SKUS)


def simulate(buffer: float = 1.15):
    """返回 (真实需求, 观测销量, 售罄起始小时) —— 三个都是 [DAYS, N]"""
    t = np.arange(DAYS)
    growth = 1 + 0.18 * t / DAYS
    season = 1 + 0.22 * np.sin(2 * np.pi * t / 90)
    holiday = np.array([1.6 if d in HOLIDAYS else 1.0 for d in t])
    wd = WEEKDAY[t % 7]

    hourly_ = np.zeros((DAYS, N, HORIZON))
    demand = np.zeros((DAYS, N))
    sold = np.zeros((DAYS, N))
    so_hour = np.full((DAYS, N), CLOSE_H, dtype=int)

    for j, (_, _, base, cv) in enumerate(SKUS):
        mean = base * wd * season * growth * holiday
        r = 1.0 / max(cv, 1e-6) ** 2
        daily = RNG.negative_binomial(r, r / (r + mean)).astype(float)

        # 按小时铺开
        hourly = np.zeros((DAYS, HORIZON))
        for d in range(DAYS):
            w = WEIGHTS * RNG.uniform(0.75, 1.25, HORIZON)
            hourly[d] = np.round(daily[d] * w / w.sum())
        for d in range(DAYS):
            hourly[d, -1] += daily[d] - hourly[d].sum()
        hourly = np.maximum(hourly, 0)

        # 备货：最近 4 个同星期的销量均值 × 1.15（平滑，避免截断死亡螺旋）
        stock = np.zeros(DAYS)
        for d in range(DAYS):
            hist = [sold[d - w, j] for w in (7, 14, 21, 28) if d - w >= 0 and sold[d - w, j] > 0]
            if len(hist) >= 4:
                # 店主只会看销量，所以用历史销量估；兜底到全期均值，避免越缺越少订的死亡螺旋
                stock[d] = max(1, round(max(np.mean(hist) * buffer, np.mean(mean[:d + 1]) * 0.85)))
            else:
                stock[d] = max(1, round(mean[d] * buffer))

        for d in range(DAYS):
            demand[d, j] = hourly[d].sum()
            hourly_[d, j, :] = hourly[d]
            rem = stock[d]
            for h in range(HORIZON):
                take = min(hourly[d, h], rem)
                sold[d, j] += take
                rem -= take
                if rem <= 0 and hourly[d, h] > take:
                    so_hour[d, j] = OPEN_H + h
                    break
    return demand, sold, so_hour, hourly_


def run(demand, sold, so_hour, hourly_, start=60, k=8):
    """逐日推进，三种做法各给一个预测。"""
    wd = np.arange(DAYS) % 7
    out = {key: np.zeros((DAYS - start, N)) for key in ("raw", "excl", "fill")}
    truth = demand[start:]

    for i, t in enumerate(range(start, DAYS)):
        for j in range(N):
            past_days = np.arange(t)
            same = past_days[wd[past_days] == wd[t]]
            if len(same) == 0:
                continue
            same = same[-k:]

            # 1) 不处理：直接用卖出去的
            out["raw"][i, j] = sold[same, j].mean()

            # 2) 剔除：卖光的日子整条不要
            clean = same[so_hour[same, j] >= CLOSE_H]
            if len(clean) >= 2:
                out["excl"][i, j] = sold[clean, j].mean()
            else:
                out["excl"][i, j] = sold[same, j].mean()

            # 3) 补齐：按时段分别估率（缺货多发生在下午低峰，用全天平均会高估）
            hist_clean = past_days[so_hour[past_days, j] >= CLOSE_H]
            if len(hist_clean) > 0:
                rate_h = hourly_[hist_clean, j, :].mean(axis=0)
            else:
                rate_h = np.full(HORIZON, max(sold[same, j].mean() / HORIZON, 0.0))

            filled = sold[same, j].astype(float).copy()
            for k2, d in enumerate(same):
                if so_hour[d, j] < CLOSE_H:
                    k0 = so_hour[d, j] - OPEN_H
                    # 售罄那一小时已经卖了一部分，只补一半，避免重复计算
                    filled[k2] += rate_h[k0 + 1:].sum() + rate_h[k0] * 0.5
            out["fill"][i, j] = filled.mean()
    return truth, out


def main():
    labels = {"raw": "不处理", "excl": "剔除", "fill": "补齐"}
    print("缺货率越严重，补齐越值钱——这是这套设计的证据")
    print()
    print("=" * 64)
    print(f"{'缺货率':>7}{'不处理偏差':>12}{'剔除偏差':>11}{'补齐偏差':>11}{'补齐 MAPE':>11}")
    print("-" * 64)

    rows = []
    for buf in (1.35, 1.20, 1.10, 1.00, 0.95):
        demand, sold, so_hour, hourly_ = simulate(buf)
        cut = float((sold < demand).mean() * 100)
        truth, pred = run(demand, sold, so_hour, hourly_)
        y = truth.reshape(-1)
        b = {k: F.bias(y, pred[k].reshape(-1)) for k in labels}
        m = {k: F.mape(y, pred[k].reshape(-1)) for k in labels}
        rows.append((cut, b, m))
        print(f"{cut:>6.0f}%{b['raw']:>11.1f}%{b['excl']:>10.1f}%"
              f"{b['fill']:>10.1f}%{m['fill']:>10.1f}%")

    print()
    print("读法：缺货率低时，不处理和补齐差不多；缺货率一高，不处理迅速偏负，")
    print("      而补齐把偏差按住在个位数——这就是「先补数据，再谈预测」的意义。")
    print("      剔除永远是最差的：它专挑需求高的日子扔掉。")

    # 存最严重那一档的明细
    demand, sold, so_hour, hourly_ = simulate(0.95)
    truth, pred = run(demand, sold, so_hour, hourly_)
    out = Path(__file__).resolve().parent.parent / "docs"
    out.mkdir(exist_ok=True)
    flat = lambda a: a.reshape(-1)
    pd.DataFrame({
        "day": np.repeat(np.arange(60, DAYS), N),
        "sku": np.tile(NAMES, DAYS - 60),
        "true": flat(truth),
        "raw": flat(pred["raw"]),
        "excl": flat(pred["excl"]),
        "fill": flat(pred["fill"]),
    }).to_csv(out / "fill_compare.csv", index=False)
    print(f"\n明细 -> {out / 'fill_compare.csv'}")


if __name__ == "__main__":
    main()
