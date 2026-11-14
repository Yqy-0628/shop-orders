# -*- coding: utf-8 -*-
"""仿真 + 四种预测 + 共形区间的滚动回测。

关键设计：模型只看得到「卖出去的」，而卖光那天的销量是被截断的。
所以多跑一档「只用没卖光的日子估均值」——这一步就是把需求补回来。

0  同星期均值（全部日子）
1  同星期均值（只用没卖光的日子）   ← 补齐
2  1 + 趋势
3  2 + 分层池化 + 日历

跑法：python scripts/backtest_forecast.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import forecast as F

RNG = np.random.default_rng(2026)

DAYS = 140
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
CAT = {s[0]: s[1] for s in SKUS}


def simulate():
    t = np.arange(DAYS)
    growth = 1 + 0.18 * t / DAYS                      # 缓慢增长 18%
    season = 1 + 0.22 * np.sin(2 * np.pi * t / 90)    # 季节起伏 ±22%
    holiday = np.array([1.6 if d in HOLIDAYS else 1.0 for d in t])
    wd = WEEKDAY[t % 7]

    truth = {}
    for name, cat, base, cv in SKUS:
        mean = base * wd * season * growth * holiday
        r = 1.0 / max(cv, 1e-6) ** 2
        truth[name] = RNG.negative_binomial(r, r / (r + mean)).astype(float)
    truth = pd.DataFrame(truth, index=t)

    stock = np.empty_like(truth.values)
    for d in range(DAYS):
        prev = truth.values[(d - 7) % DAYS] if d >= 7 else truth.values[d]
        stock[d] = np.maximum(1, np.round(prev * 1.08))
    sold = np.minimum(truth.values, stock)
    censored = sold >= stock          # 这天卖光了，销量是被截断的
    return truth, pd.DataFrame(sold, index=t, columns=truth.columns), censored


def mean_clean(v: np.ndarray, cens: np.ndarray, weekday: np.ndarray,
               t: int, k: int = 6) -> float:
    """只用「没卖光」的同星期日子求均值；不够就退回全部。"""
    wd = weekday[t]
    idx = np.where((weekday[:t] == wd) & (~cens[:t]))[0]
    if len(idx) == 0:
        idx = np.where(weekday[:t] == wd)[0]
    if len(idx) == 0:
        return float(v[:t].mean()) if t else 0.0
    return float(v[idx[-k:]].mean())


def trend_ratio(v: np.ndarray, t: int, win: int = 14) -> float:
    if t < 2 * win:
        return 1.0
    a, b = v[t - win:t].sum(), v[t - 2 * win:t - win].sum()
    return float(np.clip(a / b, 0.8, 1.25)) if b > 0 else 1.0


def run(obs, cens, start=60):
    weekday = np.arange(DAYS) % 7
    cats = sorted(set(CAT.values()))
    cat_series = {c: obs[[n for n in NAMES if CAT[n] == c]].sum(axis=1).values
                  for c in cats}
    cat_cens = {c: (cens[:, [NAMES.index(n) for n in NAMES if CAT[n] == c]].any(axis=1))
                for c in cats}

    keys = ["base", "clean", "trend", "full"]
    pred = {k: {n: [] for n in NAMES} for k in keys}
    t_idx = list(range(start, DAYS))

    for t in t_idx:
        cat_hat, share = {}, {}
        for c in cats:
            cat_hat[c] = mean_clean(cat_series[c], cat_cens[c], weekday, t)
            tot = cat_series[c][:t].sum()
            for n in NAMES:
                if CAT[n] == c:
                    share[n] = max(obs[n].values[:t].sum() / max(tot, 1e-9), 0.01)

        for n in NAMES:
            v = obs[n].values
            ci = NAMES.index(n)
            raw = F.same_weekday_mean(v, weekday, t)
            clean = mean_clean(v, cens[:, ci], weekday, t)
            anchor = cat_hat[CAT[n]] * share[n]
            pooled = F.shrink_toward(clean, anchor, max(1, t - 7), k=20.0)
            tr = trend_ratio(v, t)

            pred["base"][n].append(raw)
            pred["clean"][n].append(clean)
            pred["trend"][n].append(clean * tr)
            pred["full"][n].append(pooled * tr * hol_factor(n, t, obs))
    return t_idx, pred, keys


HOL = {}


def hol_factor(n, t, obs):
    if n not in HOL:
        v = obs[n].values
        rs = []
        for d in sorted(HOLIDAYS):
            if d < 7:
                continue
            idx = np.where((np.arange(d) % 7) == (d % 7))[0]
            base = v[idx[-4:]].mean() if len(idx) else 0
            if base > 0:
                rs.append(v[d] / base)
        HOL[n] = float(np.clip(np.mean(rs), 1.0, 2.0)) if rs else 1.4
    return HOL[n] if t in HOLIDAYS else 1.0


def main():
    truth, obs, cens = simulate()
    print(f"仿真：{DAYS} 天 × {len(SKUS)} 个单品　"
          f"卖光的天数占比 {cens.mean()*100:.1f}%")

    t_idx, pred, keys = run(obs, cens)
    y = truth.iloc[t_idx].values.reshape(-1)

    labels = {"base": "0 同星期均值（全部日子）",
              "clean": "1 只用没卖光的日子",
              "trend": "2 ＋趋势",
              "full": "3 ＋池化＋日历"}
    scores = {}
    print()
    print("=" * 64)
    print("滚动回测：逐日推进，预测次日（评分对着真实需求）")
    print("=" * 64)
    print(f"{'方法':<26}{'MAPE':>9}{'偏差':>9}")
    for k in keys:
        p = np.array([pred[k][n] for n in NAMES]).T
        scores[k] = p
        print(f"{labels[k]:<26}{F.mape(y, p.reshape(-1)):>8.1f}%"
              f"{F.bias(y, p.reshape(-1)):>8.1f}%")

    best = scores["full"]
    half = len(t_idx) // 2
    # 每个单品各算各的半宽：吐司和沙拉的误差量级差好几倍，共用一个带宽会失真
    # 有增长趋势时，绝对残差会随水平漂移 → 用相对残差（归一化共形）
    # 残差是偏的（系统性低估），对称区间必然漏上侧 → 上下各取 5% 分位，做非对称区间
    tp_all = best
    rel = (truth.iloc[t_idx[:half]].values - tp_all[:half]) / np.maximum(tp_all[:half], 1e-6)
    lo = np.quantile(rel, 0.05, axis=0)
    hi = np.quantile(rel, 0.95, axis=0)
    tt = truth.iloc[t_idx[half:]].values
    tp = tp_all[half:]
    inside = ((tt - tp) / np.maximum(tp, 1e-6) >= lo[None, :]) & \
             ((tt - tp) / np.maximum(tp, 1e-6) <= hi[None, :])
    cover = float(inside.mean() * 100)

    print()
    print(f"共形区间（逐单品校准）：校准 {half} 天 → 检验 {len(t_idx)-half} 天")
    for j, n in enumerate(NAMES):
        print(f"  {n:<14} 区间 {lo[j]*100:>+4.0f}% ~ {hi[j]*100:>+4.0f}%　覆盖率 {inside[:, j].mean()*100:>5.1f}%")
    print(f"  合计覆盖率 {cover:.1f}%")

    m0 = F.mape(y, scores["base"].reshape(-1))
    m3 = F.mape(y, best.reshape(-1))
    b0 = F.bias(y, scores["base"].reshape(-1))
    b3 = F.bias(y, best.reshape(-1))
    print(f"\nMAPE  {m0:.1f}% → {m3:.1f}%（降 {m0-m3:.1f} 点）")
    print(f"偏差  {b0:+.1f}% → {b3:+.1f}%（修正 {abs(b0-b3):.1f} 点）")

    out = Path(__file__).resolve().parent.parent / "docs"
    out.mkdir(exist_ok=True)
    flat = lambda a: a.reshape(-1)
    pd.DataFrame({
        "day": np.repeat(t_idx, len(NAMES)),
        "sku": np.tile(NAMES, len(t_idx)),
        "true": flat(truth.iloc[t_idx].values),
        "base": flat(scores["base"]), "clean": flat(scores["clean"]),
        "trend": flat(scores["trend"]), "full": flat(scores["full"]),
    }).to_csv(out / "forecast_backtest.csv", index=False)
    print(f"-> {out / 'forecast_backtest.csv'}")


if __name__ == "__main__":
    main()
