# -*- coding: utf-8 -*-
"""用 WAPE / WPE 重新给预测打分（比 MAPE 更贴近老板的直觉）。

为什么换指标：
  MAPE 把每个单品每天都当成一样重，19 件的贝果和 32 件的牛奶差 5 件，
  两者在 MAPE 里各占一份，但老板真正感受到的是「一天总共少卖了多少件」。
  WAPE = Σ|预测−真值| / Σ真值，按件数加权，回答的就是这个问题。
  WPE  = Σ(预测−真值) / Σ真值，看的是方向性偏差（正=备货偏多，负=偏少）。

跑法：python scripts/eval_wape.py   （结果同时写 docs/eval_wape.csv）
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "scripts"))
import eval_truth as T   # 复用「重建真值 + 滚动回测」

from core import connect

MODES = (("fill", "平均率补齐"), ("raw", "直接用销量"), ("clean", "只用干净日"))


def wape(y, p):
    denom = float(np.abs(y).sum())
    return float(np.abs(p - y).sum() / denom * 100) if denom else 0.0


def wpe(y, p):
    denom = float(np.abs(y).sum())
    return float((p - y).sum() / denom * 100) if denom else 0.0


def category_of():
    return {r["sku_id"]: r["category"]
            for r in connect().execute("SELECT sku_id, category FROM sku")}


def main():
    truth, sold_q, so_hour = T.rebuild()
    cat = category_of()

    acc = {k: ([], []) for k, _ in MODES}
    cat_acc = {}
    days = []

    for s in T.mdd.SKUS:
        sku = s["sku_id"]
        df = T.series(sku, sold_q, so_hour)

        preds = {}
        for k, _ in MODES:
            y, p, lo, hi = T.backtest(df, truth, sku, k)
            preds[k] = p
            acc[k][0].append(y)
            acc[k][1].append(p)

            c = cat.get(sku, "其他")
            cy, cp = cat_acc.setdefault(c, ([], []))
            cy.append(y)
            cp.append(p)
        days.append((s, df, preds))

    out = []
    print("=" * 78)
    print("WAPE / WPE：按件数加权，回答「一天总共差多少件」")
    print("=" * 78)
    print(f"{'口径':<14}{'MAPE':>9}{'WAPE':>9}{'WPE':>9}{'样本':>7}")
    for k, name in MODES:
        Y = np.concatenate(acc[k][0])
        P = np.concatenate(acc[k][1])
        out.append(dict(口径=name, MAPE=T.mape(Y, P), WAPE=wape(Y, P),
                        WPE=wpe(Y, P), 样本=len(Y)))
        print(f"{name:<14}{T.mape(Y, P):>8.1f}%{wape(Y, P):>8.1f}%"
              f"{wpe(Y, P):>+8.1f}%{len(Y):>7d}")

    print()
    print("按品类看（口径：平均率补齐）")
    print("-" * 78)
    print(f"{'品类':<10}{'WAPE':>9}{'WPE':>9}{'样本':>7}")
    for c, (cy, cp) in cat_acc.items():
        Y = np.concatenate(cy)
        P = np.concatenate(cp)
        print(f"{c:<10}{wape(Y, P):>8.1f}%{wpe(Y, P):>+8.1f}%{len(Y):>7d}")
        out.append(dict(口径=f"品类·{c}", MAPE=float("nan"),
                        WAPE=wape(Y, P), WPE=wpe(Y, P), 样本=len(Y)))

    # 一天一天看：店主每天只关心当天总量
    print()
    print("逐日总量误差（口径：平均率补齐，取最靠后 14 天）")
    print("-" * 78)
    per_day = {}
    for s, df, preds in days:
        sku = s["sku_id"]
        idx = 0
        for i in range(56, len(df)):
            y = truth[(sku, T.mdd.DAYS[i])]
            if y < 3:
                continue
            p = float(preds["fill"][idx])
            idx += 1
            per_day.setdefault(T.mdd.DAYS[i].isoformat(), []).append((y, p))

    recent = sorted(per_day)[-14:]
    print(f"{'日期':<13}{'真值合计':>9}{'预测合计':>9}{'差':>7}{'WAPE':>9}")
    for day in recent:
        ys = np.array([a for a, _ in per_day[day]], float)
        ps = np.array([b for _, b in per_day[day]], float)
        print(f"{day:<13}{ys.sum():>9.0f}{ps.sum():>9.0f}"
              f"{ps.sum() - ys.sum():>+7.0f}{wape(ys, ps):>8.1f}%")

    frame = pd.DataFrame(out)
    path = ROOT / "docs" / "eval_wape.csv"
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    print()
    print(f"已写 {path}")


if __name__ == "__main__":
    main()
