# -*- coding: utf-8 -*-
"""指标口径：缺货率、报损率、损失金额、品类偏差。"""
import datetime as dt
from statistics import NormalDist

from . import demand as D

DEMO_TODAY = "2026-11-09"
SEED_END = "2026-11-08"   # 统计只认种子窗口，演示当天写入的记录不参与


def stock_rows(conn, day):
    """某天每个 SKU 的结余 = 当日实物变动（已到货）− 当日销售。"""
    return conn.execute(
        """
        SELECT s.sku_id, s.name, s.category, s.price, s.cost, s.salvage,
               COALESCE(m.qty,0) - COALESCE(x.qty,0) AS qty,
               COALESCE(inc.qty,0) AS incoming
        FROM sku s
        LEFT JOIN (SELECT sku_id, SUM(qty) qty FROM stock_move
                   WHERE day=? AND status='已到货' GROUP BY sku_id) m ON m.sku_id = s.sku_id
        LEFT JOIN (SELECT sku_id, SUM(qty) qty FROM stock_move
                   WHERE day=? AND status='在途' GROUP BY sku_id) inc ON inc.sku_id = s.sku_id
        LEFT JOIN (SELECT sku_id, SUM(qty) qty FROM sales
                   WHERE day=? GROUP BY sku_id) x ON x.sku_id = s.sku_id
        ORDER BY s.category, s.sku_id
        """,
        (day, day, day),
    ).fetchall()


def ensure_today(conn, day=DEMO_TODAY):
    """第一次打开时给“今天”生成一张进货单（按上周同星期销量 × 1.08）。

    逐个 SKU 判断，已经有的就不再补——否则反复启动会把库存越堆越多。
    """
    have = {r[0] for r in conn.execute(
        "SELECT DISTINCT sku_id FROM stock_move WHERE day=?", (day,))}
    # 上周同一天，不是“历史上所有星期二”——后者会把 12 周的销量加在一起
    prev = (dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat()
    rows = conn.execute(
        "SELECT sku_id, SUM(qty) q FROM sales WHERE day=? GROUP BY sku_id", (prev,)
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """SELECT sku_id, ROUND(mu * 1.0) q FROM sku""").fetchall()
    added = 0
    for r in rows:
        if r["sku_id"] in have:
            continue
        qty = max(1, int(round(r["q"] * 1.08)))
        cost = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (r["sku_id"],)).fetchone()[0]
        conn.execute(
            "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
            "VALUES (?,?,'入库',?,?,'已到货')",
            (r["sku_id"], day, qty, cost),
        )
        added += 1
    conn.commit()
    return added > 0


def kpi(conn):
    rates = D.hourly_rates(conn)
    perishable = {r[0] for r in conn.execute(
        "SELECT sku_id FROM sku WHERE shelf_life_days=1")}
    so_loss = 0.0
    so_hours = 0
    for r in conn.execute(
        "SELECT sku_id, day, start_hour, end_hour FROM stockout_mark WHERE day<=?",
        (SEED_END,),
    ):
        # 只统计易损品，和报损同口径——否则两个损失不可比
        if r["sku_id"] not in perishable:
            so_hours += D.missing_hours(r["start_hour"], r["end_hour"])
            continue
        miss = D.missing_hours(r["start_hour"], r["end_hour"])
        wd = conn.execute(
            "SELECT weekday FROM sales WHERE sku_id=? AND day=? LIMIT 1",
            (r["sku_id"], r["day"]),
        ).fetchone()
        if not wd:
            continue
        s = conn.execute(
            "SELECT price, cost FROM sku WHERE sku_id=?", (r["sku_id"],)
        ).fetchone()
        so_loss += miss * rates.get((r["sku_id"], wd["weekday"]), 0.0) * (s["price"] - s["cost"])
        so_hours += miss

    # 报损是记录下来的事实，不是从“进货减销售”倒推的
    sp_loss = 0.0
    sp_qty = 0
    for r in conn.execute(
        "SELECT m.qty, s.cost FROM stock_move m JOIN sku s ON s.sku_id=m.sku_id "
        "WHERE m.type='报损' AND m.day<=?",
        (SEED_END,),
    ):
        sp_qty += abs(r["qty"])
        sp_loss += abs(r["qty"]) * r["cost"]

    in_qty = conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM stock_move WHERE type='入库' AND day<=?",
        (SEED_END,),
    ).fetchone()[0]

    days = conn.execute(
        "SELECT COUNT(DISTINCT day) FROM sales WHERE day<=?", (SEED_END,)
    ).fetchone()[0]
    total_hours = max(1, days * (D.CLOSE_H - D.OPEN_H) * 20)
    return dict(
        stockout_rate=so_hours / total_hours,
        spoilage_rate=(sp_qty / in_qty) if in_qty else 0,
        stockout_loss=so_loss,
        spoilage_loss=sp_loss,
        ratio=(so_loss / sp_loss) if sp_loss else 0,
    )


def category_deviation(conn):
    """每个品类：实际订货 vs 建议订货 的平均偏差。"""
    out = []
    for c in conn.execute("SELECT DISTINCT category FROM sku ORDER BY category"):
        cat = c["category"]
        rows = conn.execute(
            """SELECT s.mu, s.sigma, s.cost, s.price, s.salvage,
                      (SELECT AVG(qty) FROM stock_move m
                       WHERE m.sku_id=s.sku_id AND m.type='入库') AS avg_order
               FROM sku s WHERE s.category=?""",
            (cat,),
        ).fetchall()
        actual = sum(r["avg_order"] or 0 for r in rows) / len(rows)
        suggest = 0.0
        for r in rows:
            cu, co = r["price"] - r["cost"], r["cost"] - r["salvage"]
            z = NormalDist().inv_cdf(cu / (cu + co))
            suggest += r["mu"] + z * r["sigma"]
        suggest /= len(rows)
        out.append(dict(category=cat, actual=actual, suggest=suggest,
                        gap=(actual - suggest) / suggest))
    return out
