# -*- coding: utf-8 -*-
"""历史回放对照 + 安全系数敏感性。

A 经验法（上周同星期销量 × 系数）
B 经验法 + 售罄补齐
C 报童 Q*

核心结论：经验法只要把系数猜对，也能接近最优；
但没人知道该猜多少，猜偏一点代价就翻倍。
跑法：python scripts/backtest.py
"""
import random
import statistics
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

OPEN_H, CLOSE_H = 9, 21
HOURS = range(OPEN_H, CLOSE_H)
WEIGHTS = [0.40, 0.50, 0.60, 0.90, 1.20, 1.50, 1.40, 1.00, 0.90, 0.80, 0.70, 0.60]
WEEKDAY = {0: 0.92, 1: 0.88, 2: 0.96, 3: 1.00, 4: 1.14, 5: 1.30, 6: 1.24}
DAYS = 84
BUFFER = 1.08

TEMPLATES = [
    ("烘焙", 12.0, 6.0, 2.4, 1, 18, 5),
    ("鲜食", 15.0, 8.0, 3.0, 1, 14, 5),
    ("饮品", 9.0, 3.0, 2.4, 1, 12, 5),
    ("日配", 6.0, 3.6, 1.8, 3, 30, 5),
]


def make_skus(rng):
    out = []
    for cat, price, cost, salvage, shelf, mu0, n in TEMPLATES:
        for i in range(n):
            mu = mu0 * rng.uniform(0.85, 1.15)
            out.append(dict(id=f"{cat}{i}", cat=cat, price=price, cost=cost,
                            salvage=salvage, shelf=shelf, mu=mu,
                            sigma=4.0 if cat == "饮品" else mu * 0.18))
    return out


def z_of(p):
    from statistics import NormalDist
    return NormalDist().inv_cdf(min(max(p, 0.001), 0.999))


def q_star(sku, wd):
    cu = sku["price"] - sku["cost"]
    co = max(0.01, sku["cost"] - sku["salvage"])
    mu = sku["mu"] * WEEKDAY[wd]
    return max(0.0, mu + z_of(cu / (cu + co)) * sku["sigma"])


def spread(total, rng):
    noise = [w * rng.uniform(0.75, 1.25) for w in WEIGHTS]
    s = sum(noise)
    out, acc = [], 0
    for w in noise[:-1]:
        q = int(round(total * w / s))
        out.append(q)
        acc += q
    out.append(max(0, total - acc))
    return out


def simulate(skus, demand, policy, rng, buffer=BUFFER):
    hist_sold, hist_true, rate_acc = {}, {}, {}
    stat = dict(miss_hours=0, hours=0, spoilage=0, ordered=0,
                loss_stock=0.0, loss_spoil=0.0, loss_stock_per=0.0)

    for d in range(DAYS):
        wd = d % 7
        for sku in skus:
            key = (sku["id"], wd)
            if policy == "C":
                order = int(round(q_star(sku, wd)))
            else:
                src = hist_sold if policy == "A" else hist_true
                past = src.get(key, [])
                order = (int(round(statistics.mean(past[-4:]) * buffer)) if past
                         else int(round(sku["mu"] * WEEKDAY[wd])))
            order = max(1, order)

            true_d = demand[(sku["id"], d)]
            hourly = spread(true_d, rng)
            rem, sold, miss_h = order, 0, 0
            for h, want in zip(HOURS, hourly):
                take = min(want, rem)
                sold += take
                rem -= take
                if rem <= 0 and want > take:
                    miss_h = CLOSE_H - h
                    break

            unmet = max(0, true_d - sold)
            stat["loss_stock"] += unmet * (sku["price"] - sku["cost"])
            if sku["shelf"] == 1:
                stat["loss_stock_per"] += unmet * (sku["price"] - sku["cost"])
            stat["miss_hours"] += miss_h
            stat["hours"] += (CLOSE_H - OPEN_H)
            stat["ordered"] += order
            if sku["shelf"] == 1:
                left = max(0, order - sold)
                stat["spoilage"] += left
                stat["loss_spoil"] += left * sku["cost"]

            hist_sold.setdefault(key, []).append(sold)
            acc = rate_acc.setdefault(key, [0, 0])
            if miss_h == 0:
                acc[0] += sold
                acc[1] += (CLOSE_H - OPEN_H)
            rate = (acc[0] / acc[1]) if acc[1] else (sku["mu"] * WEEKDAY[wd] / (CLOSE_H - OPEN_H))
            hist_true.setdefault(key, []).append(sold + miss_h * rate)
    return stat


def draw(curve, qs_total, path):
    W, H = 1560, 620
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    fb = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 30)
    fr = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
    fs = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 21)

    x0, x1 = 120, 1500
    y0, y1 = 90, 520
    vmin = min(r["total"] for r in curve) * 0.96
    vmax = max(r["total"] for r in curve) * 1.02

    def px(i):
        return x0 + i * (x1 - x0) / (len(curve) - 1)

    def py(v):
        return y1 - (v - vmin) / (vmax - vmin) * (y1 - y0)

    d.line([x0, y1, x1, y1], fill=(210, 216, 226), width=2)
    d.line([x0, y0, x0, y1], fill=(210, 216, 226), width=2)

    # 报童基准线
    yy = py(qs_total)
    for i in range(0, x1 - x0, 26):
        d.line([x0 + i, yy, x0 + i + 13, yy], fill=(46, 84, 150), width=3)
    d.text((x0 + 14, yy - 34), f"报童 Q*（不猜系数）：{qs_total:,.0f} 元",
           font=fs, fill=(46, 84, 150))

    pts = [(px(i), py(r["total"])) for i, r in enumerate(curve)]
    d.line(pts, fill=(176, 58, 58), width=5, joint="curve")
    best = min(range(len(curve)), key=lambda i: curve[i]["total"])
    for i, (x, y) in enumerate(pts):
        col = (46, 84, 150) if i == best else (176, 58, 58)
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=col)

    for i, r in enumerate(curve):
        d.text((px(i) - 26, y1 + 14), f"×{r['buf']:.2f}", font=fr, fill=(110, 118, 128))
        if i in (0, 2, 4, 6):
            d.text((px(i) - 30, py(r["total"]) - 40), f"{r['total']:,.0f}",
                   font=fr, fill=(90, 98, 112))

    d.text((px(best) - 90, py(curve[best]["total"]) - 78), "经验法的最好成绩",
           font=fs, fill=(46, 84, 150))
    d.text((60, 24), "同一段需求：凭经验订货，猜错系数要付多少", font=fb, fill=(31, 56, 100))
    img.save(path)


def main():
    rng = random.Random(2026)
    skus = make_skus(rng)
    demand = {}
    for d in range(DAYS):
        wd = d % 7
        for s in skus:
            demand[(s["id"], d)] = max(0, int(round(
                s["mu"] * WEEKDAY[wd] * rng.gauss(1.0, 0.18))))

    rows = []
    for name, key in [("A 经验法", "A"), ("B 经验法+补齐", "B"), ("C 报童 Q*", "C")]:
        st = simulate(skus, demand, key, random.Random(7))
        rows.append(dict(name=name, total=st["loss_stock"] + st["loss_spoil"],
                         stock=st["loss_stock"], spoil=st["loss_spoil"],
                         sr=st["miss_hours"] / st["hours"],
                         pr=st["spoilage"] / max(1, st["ordered"])))

    print("=" * 72)
    print(f"三档策略（系数固定 {BUFFER}）　{DAYS} 天 × {len(skus)} 个 SKU")
    print("=" * 72)
    print(f"{'策略':<16}{'缺货率':>8}{'报损率':>8}{'缺货损失':>10}{'报损损失':>10}{'总代价':>10}")
    for r in rows:
        print(f"{r['name']:<16}{r['sr']*100:>7.1f}%{r['pr']*100:>7.1f}%"
              f"{r['stock']:>10.0f}{r['spoil']:>10.0f}{r['total']:>10.0f}")

    a, b, c = rows
    print(f"\n  补数据（A→B）{100*(1-b['total']/a['total']):+.0f}%　"
          f"换模型（B→C）{100*(1-c['total']/b['total']):+.0f}%　"
          f"合计（A→C）{100*(1-c['total']/a['total']):+.0f}%")

    curve = []
    for buf in [0.95, 1.00, 1.05, 1.08, 1.15, 1.20, 1.25, 1.35]:
        st = simulate(skus, demand, "A", random.Random(7), buffer=buf)
        curve.append(dict(buf=buf, total=st["loss_stock"] + st["loss_spoil"]))

    print()
    print("=" * 72)
    print("经验法的安全系数猜错多少，代价差多少")
    print("=" * 72)
    best = min(curve, key=lambda r: r["total"])
    for r in curve:
        gap = (r["total"] - best["total"]) / best["total"] * 100
        print(f"  ×{r['buf']:.2f}　{r['total']:>8.0f} 元　{gap:+6.1f}%")
    print(f"  {'报童 Q*':<6}{c['total']:>10.0f} 元　"
          f"{(c['total']-best['total'])/best['total']*100:+6.1f}%（不需要猜）")

    draw(curve, c["total"], DOCS / "backtest.png")
    print(f"\n-> {DOCS / 'backtest.png'}")


if __name__ == "__main__":
    main()
