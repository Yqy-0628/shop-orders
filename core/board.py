# -*- coding: utf-8 -*-
"""经营看板的数据口径：逐日趋势、品类损失、三条自动提示。

只做聚合与规则，不引入模型，保证每个数字都能用 SQL 复算。
"""
import datetime as dt

from . import connect
from .metrics import SEED_END, kpi


def _window(conn, days):
    """取有数据的那一段：末端不越过种子窗口，避免演示当天的记录混进来。"""
    end = conn.execute(
        "SELECT MAX(day) FROM sales WHERE day<=?", (SEED_END,)).fetchone()[0]
    if not end:
        return None, None
    d_end = dt.date.fromisoformat(end)
    d_start = d_end - dt.timedelta(days=days - 1)
    return d_start.isoformat(), d_end.isoformat()


def daily_trend(days=28, conn=None):
    """逐日：卖出多少、进了多少、几个单品卖光、当天营业额与毛利。"""
    conn = conn or connect()
    start, end = _window(conn, days)
    if not start:
        return []

    sold = {}
    for r in conn.execute(
        """SELECT x.day AS day,
                  SUM(x.qty) AS qty,
                  SUM(x.qty * x.unit_price) AS revenue,
                  SUM(x.qty * (x.unit_price - k.cost)) AS gross
           FROM sales x JOIN sku k ON k.sku_id = x.sku_id
           WHERE x.day BETWEEN ? AND ?
           GROUP BY x.day""", (start, end)):
        sold[r["day"]] = r

    ordered = {r["day"]: r["qty"] for r in conn.execute(
        """SELECT day, SUM(qty) AS qty FROM stock_move
           WHERE type='入库' AND status='已到货' AND day BETWEEN ? AND ?
           GROUP BY day""", (start, end))}

    out = {r["day"]: r["n"] for r in conn.execute(
        """SELECT day, COUNT(DISTINCT sku_id) AS n FROM stockout_mark
           WHERE day BETWEEN ? AND ? GROUP BY day""", (start, end))}

    rows, day = [], dt.date.fromisoformat(start)
    while day <= dt.date.fromisoformat(end):
        k = day.isoformat()
        r = sold.get(k)
        rows.append(dict(
            day=k,
            sold=int(r["qty"] or 0) if r else 0,
            ordered=int(ordered.get(k, 0) or 0),
            stockouts=int(out.get(k, 0) or 0),
            revenue=float(r["revenue"] or 0) if r else 0.0,
            gross=float(r["gross"] or 0) if r else 0.0,
        ))
        day += dt.timedelta(days=1)
    return rows


def category_loss(days=28, conn=None):
    """按品类：报损花了多少钱、卖光了多少天、进了多少件。"""
    conn = conn or connect()
    start, end = _window(conn, days)
    if not start:
        return []

    cat = {}
    for r in conn.execute(
        """SELECT k.category AS category,
                  COALESCE(SUM(CASE WHEN m.type='报损' THEN ABS(m.qty)*k.cost END),0) AS waste_cost,
                  COALESCE(SUM(CASE WHEN m.type='报损' THEN ABS(m.qty) END),0) AS waste_qty,
                  COALESCE(SUM(CASE WHEN m.type='入库' THEN m.qty END),0) AS in_qty
           FROM sku k LEFT JOIN stock_move m
             ON m.sku_id = k.sku_id AND m.day BETWEEN ? AND ?
           GROUP BY k.category""", (start, end)):
        cat[r["category"]] = dict(
            category=r["category"], waste_cost=float(r["waste_cost"]),
            waste_qty=int(r["waste_qty"]), in_qty=int(r["in_qty"]),
            soldout_days=0)

    for r in conn.execute(
        """SELECT k.category AS category, COUNT(*) AS n
           FROM stockout_mark s JOIN sku k ON k.sku_id = s.sku_id
           WHERE s.day BETWEEN ? AND ?
           GROUP BY k.category""", (start, end)):
        if r["category"] in cat:
            cat[r["category"]]["soldout_days"] = int(r["n"])

    rows = list(cat.values())
    for r in rows:
        r["waste_rate"] = (r["waste_qty"] / r["in_qty"]) if r["in_qty"] else 0.0
    return sorted(rows, key=lambda r: -r["waste_cost"])


def headline(days=28, conn=None):
    """三条最该做的事：不带模型，只按阈值，每句都能被数字追出来。"""
    conn = conn or connect()
    start, end = _window(conn, 7)
    tips = []

    # 1) 最近 7 天卖光最多的单品
    for r in conn.execute(
        """SELECT s.sku_id AS sku_id, k.name AS name, COUNT(*) AS n
           FROM stockout_mark s JOIN sku k ON k.sku_id = s.sku_id
           WHERE s.day BETWEEN ? AND ?
           GROUP BY s.sku_id ORDER BY n DESC LIMIT 2""", (start, end)):
        tips.append(dict(kind="提量", sku=r["name"], value=r["n"],
                         text=f"近 7 天卖光 {r['n']} 天，明天可多订一点"))

    # 2) 报损率最高的品类
    cats = category_loss(days, conn)
    bad = [c for c in cats if c["in_qty"] >= 50 and c["waste_rate"] >= 0.15]
    for c in bad[:1]:
        tips.append(dict(kind="降量", sku=c["category"], value=c["waste_rate"],
                         text=f"报损率 {c['waste_rate']*100:.0f}%，高于 15%，"
                               f"该品类可以少订"))

    # 3) 全店的钱主要漏在哪
    s = kpi(conn)
    if s["spoilage_loss"]:
        if s["ratio"] >= 1:
            tips.append(dict(kind="结构", sku="全店", value=s["ratio"],
                             text=f"缺货损失是报损的 {s['ratio']:.1f} 倍，"
                                  f"整体订得偏保守，宁多勿少"))
        else:
            tips.append(dict(kind="结构", sku="全店", value=s["ratio"],
                             text=f"报损是缺货损失的 {1/s['ratio']:.1f} 倍，"
                                  f"整体订多了，该收一收"))

    return tips
