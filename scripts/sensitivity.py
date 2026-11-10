# -*- coding: utf-8 -*-
"""敏感性：经验法的安全系数只要猜错一点，代价波动多大；模型不需要猜。"""
import importlib.util
import random
import sys

spec = importlib.util.spec_from_file_location(
    "bt", r"D:\dpwenzhang\shop-orders\scripts\backtest.py")
bt = importlib.util.module_from_spec(spec)
sys.modules["bt"] = bt
spec.loader.exec_module(bt)

rng = random.Random(2026)
skus = bt.make_skus(rng)
demand = {}
for d in range(bt.DAYS):
    wd = d % 7
    for s in skus:
        v = s["mu"] * bt.WEEKDAY[wd] * rng.gauss(1.0, 0.18)
        demand[(s["id"], d)] = max(0, int(round(v)))

print(f"{'经验法缓冲':<12}{'缺货率':>8}{'报损率':>8}{'总代价':>10}")
base = None
for buf in [0.95, 1.00, 1.05, 1.08, 1.15, 1.25, 1.35]:
    bt.BUFFER = buf
    st = bt.simulate(skus, demand, "A", random.Random(7))
    total = st["loss_stock"] + st["loss_spoil"]
    if base is None:
        base = total
    print(f"×{buf:<11.2f}{st['miss_hours']/st['hours']*100:>7.1f}%"
          f"{st['spoilage']/max(1,st['ordered'])*100:>7.1f}%{total:>10.0f}")

bt.BUFFER = 1.08
st = bt.simulate(skus, demand, "C", random.Random(7))
print(f"\n{'报童 Q*':<12}{st['miss_hours']/st['hours']*100:>7.1f}%"
      f"{st['spoilage']/max(1,st['ordered'])*100:>7.1f}%"
      f"{st['loss_stock']+st['loss_spoil']:>10.0f}   ← 不需要猜系数")
