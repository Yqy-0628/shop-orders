# -*- coding: utf-8 -*-
"""截断实验：证明「售罄补齐」能把被低估的需求补回来。

真值来自 data/uci_daily.csv（UCI Online Retail 的真实日销量）。
我们按小时铺开，模拟「订少了 → 中途售罄」，再用两种办法估需求：

  A 朴素法：直接用卖出去的件数（多数 POS 就这么干）
  B 补齐法：卖出的件数 + 缺货时长 × 同时段历史销量率

跑法：python scripts/backtest_truncation.py
"""
import csv
import datetime as dt
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

OPEN_H, CLOSE_H = 9, 21
WEIGHTS = [0.40, 0.50, 0.60, 0.90, 1.20, 1.50, 1.40, 1.00, 0.90, 0.80, 0.70, 0.60]
BUFFER = 1.15


def spread(total, weights, rng):
    sw = sum(weights)
    noise = [w * rng.uniform(0.75, 1.25) for w in weights]
    sn = sum(noise)
    out, acc = [], 0
    for w in noise[:-1]:
        q = int(round(total * w / sn))
        out.append(q)
        acc += q
    out.append(max(0, total - acc))
    return out


def simulate(series, rng):
    """series: [(date, true_qty)] -> 每日 observed"""
    past, rows = [], []
    for day, true_q in series:
        if len(past) >= 7:
            order = max(1, int(round(statistics.mean(past[-7:]) * BUFFER)))
        else:
            order = max(1, int(round(true_q)))

        hourly = spread(true_q, WEIGHTS, rng)
        rem, sold, miss = order, 0, 0
        for h, want in zip(range(OPEN_H, CLOSE_H), hourly):
            take = min(want, rem)
            sold += take
            rem -= take
            if rem <= 0 and want > take:
                miss = CLOSE_H - h
                break
        past.append(sold)
        rows.append(dict(day=day, true=true_q, sold=sold, miss=miss, order=order))
    return rows


def estimate(rows):
    """补齐法：用没有缺货的日子估出「每小时卖多少」，再补回缺货时长。"""
    by_wd = {}
    for r in rows:
        if r["miss"] == 0 and r["true"] > 0:
            by_wd.setdefault(r["day"].weekday(), []).append(r["sold"] / (CLOSE_H - OPEN_H))
    rate = {k: statistics.mean(v) for k, v in by_wd.items()}
    fallback = statistics.mean(rate.values()) if rate else 1.0
    for r in rows:
        h = rate.get(r["day"].weekday(), fallback)
        r["est"] = r["sold"] + r["miss"] * h
    return rows


def mape(rows, key):
    errs = [abs(r[key] - r["true"]) / r["true"] for r in rows if r["true"] >= 3]
    return sum(errs) / len(errs)


def bias(rows, key):
    return statistics.mean((r[key] - r["true"]) / r["true"] for r in rows if r["true"] >= 3)


def load_series():
    path = DATA / "uci_daily.csv"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        return [(dt.date.fromisoformat(r["day"]), int(r["qty"])) for r in rows], "UCI 真实流水"
    print("没有 uci_daily.csv，用合成序列代替（结论仍成立，但说服力弱）")
    rng = random.Random(7)
    base = dt.date(2025, 1, 1)
    out = []
    for i in range(240):
        q = max(1, int(round(28 * rng.gauss(1, 0.25))))
        out.append((base + dt.timedelta(days=i), q))
    return out, "合成序列"


def svg(rows, path, n=60):
    sub = rows[-n:]
    W, H, PAD = 860, 360, 46
    top = max(max(r["true"], r["est"]) for r in sub) * 1.12
    def x(i): return PAD + i * (W - 2 * PAD) / (len(sub) - 1)
    def y(v): return H - PAD - v / top * (H - 2 * PAD)
    def poly(key, color, width):
        pts = " ".join(f"{x(i):.1f},{y(r[key]):.1f}" for i, r in enumerate(sub))
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"/>'
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Microsoft YaHei, sans-serif">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="#bbb"/>',
        f'<line x1="{PAD}" y1="{PAD}" x2="{PAD}" y2="{H-PAD}" stroke="#bbb"/>',
        poly("true", "#1F3864", 2.4),
        poly("est", "#C00000", 2.0),
        poly("sold", "#9aa5b1", 1.4),
        f'<text x="{PAD}" y="26" font-size="16" fill="#1F3864" font-weight="bold">'
        f'真实需求 vs 两种估计（最近 {n} 天）</text>',
        f'<text x="{W-330}" y="{PAD+6}" font-size="13" fill="#1F3864">— 真实需求</text>',
        f'<text x="{W-330}" y="{PAD+26}" font-size="13" fill="#C00000">— 补齐后估计</text>',
        f'<text x="{W-330}" y="{PAD+46}" font-size="13" fill="#9aa5b1">— 只看销量（朴素法）</text>',
        "</svg>",
    ]
    path.write_text("\n".join(parts), encoding="utf-8")


def main():
    series, src = load_series()
    rng = random.Random(42)
    rows = estimate(simulate(series, rng))

    m_naive, m_est = mape(rows, "sold"), mape(rows, "est")
    b_naive, b_est = bias(rows, "sold"), bias(rows, "est")
    cover = sum(1 for r in rows if r["miss"] > 0) / len(rows)
    hours = sum(r["miss"] for r in rows)

    print("=" * 62)
    print(f"截断实验　数据源：{src}　{len(rows)} 天")
    print("=" * 62)
    print(f"  有售罄的天数占比   {cover*100:>6.1f}%")
    print(f"  累计缺货时长       {hours:>6.0f} 小时")
    print()
    print(f"{'方法':<14}{'平均绝对误差':>12}{'系统偏差':>12}")
    print(f"{'只看销量':<14}{m_naive*100:>11.1f}%{b_naive*100:>11.1f}%")
    print(f"{'补齐后':<14}{m_est*100:>11.1f}%{b_est*100:>11.1f}%")
    print()
    print(f"  误差降低 {(m_naive-m_est)/m_naive*100:.0f}%，"
          f"偏差从 {b_naive*100:+.1f}% 收敛到 {b_est*100:+.1f}%")

    with open(DATA / "truncation_result.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "true", "sold", "est", "miss_hours", "order"])
        for r in rows:
            w.writerow([r["day"], r["true"], r["sold"], round(r["est"], 2),
                        r["miss"], r["order"]])
    svg(rows, DATA / "truncation.svg")
    print(f"\n-> data/truncation_result.csv  data/truncation.svg")


if __name__ == "__main__":
    main()
