# -*- coding: utf-8 -*-
"""σ 敏感性：需求波动假设从 0.18 换到 0.5，结论会不会翻。

我们仿真默认 σ = 0.18μ。真实批发数据算出来 CV 是 2.0+，
但那是补货节奏不是终端需求，不能直接搬。
所以退一步：看结论对 σ 有多敏感。

跑法：python scripts/sigma_sensitivity.py
"""
import importlib.util
import random
import sys

spec = importlib.util.spec_from_file_location(
    "bt", r"D:\dpwenzhang\shop-orders\scripts\backtest.py")
bt = importlib.util.module_from_spec(spec)
sys.modules["bt"] = bt
spec.loader.exec_module(bt)

print(f"{'σ/μ':>6}{'缺货率':>9}{'报损率':>9}{'缺货损失':>11}{'报损损失':>11}"
      f"{'倍数':>8}{'总代价':>11}")
print("-" * 66)

for ratio in [0.18, 0.25, 0.30, 0.40, 0.50]:
    rng = random.Random(2026)
    skus = bt.make_skus(rng)
    for s in skus:
        s["sigma"] = s["mu"] * ratio
    demand = {}
    for d in range(bt.DAYS):
        wd = d % 7
        for s in skus:
            demand[(s["id"], d)] = max(0, int(round(
                s["mu"] * bt.WEEKDAY[wd] * rng.gauss(1.0, ratio))))

    st = bt.simulate(skus, demand, "A", random.Random(7), buffer=1.08)
    ratio_loss = st["loss_stock_per"] / st["loss_spoil"] if st["loss_spoil"] else 0
    total = st["loss_stock"] + st["loss_spoil"]
    print(f"{ratio:>6.2f}{st['miss_hours']/st['hours']*100:>8.1f}%"
          f"{st['spoilage']/max(1,st['ordered'])*100:>8.1f}%"
          f"{st['loss_stock']:>11.0f}{st['loss_spoil']:>11.0f}"
          f"{ratio_loss:>8.2f}{total:>11.0f}")

print("\n注：倍数 = 易损品缺货损失 ÷ 报损损失，和主报告同口径。")
