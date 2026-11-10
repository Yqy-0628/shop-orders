# -*- coding: utf-8 -*-
"""需求补齐：把被截断的销量还原成真实需求。

真实需求 = 实际销量 + 缺货时长 × 同时段历史销量率
"""
OPEN_H, CLOSE_H = 9, 21


def missing_hours(start_hour: int, end_hour: int = CLOSE_H) -> int:
    return max(0, min(end_hour, CLOSE_H) - max(start_hour, OPEN_H))


def hourly_rates(conn):
    """每个 (sku, weekday) 在【没有缺货的记录日】里的平均每小时销量。"""
    bad = {(r[0], r[1]) for r in conn.execute("SELECT sku_id, day FROM stockout_mark")}
    acc = {}
    for sku, day, wd, qty in conn.execute(
        "SELECT sku_id, day, weekday, SUM(qty) FROM sales GROUP BY sku_id, day, weekday"
    ):
        if (sku, day) in bad:
            continue
        key = (sku, wd)
        total, hours = acc.get(key, (0, 0))
        acc[key] = (total + qty, hours + (CLOSE_H - OPEN_H))
    return {k: (t / h if h else 0.0) for k, (t, h) in acc.items()}


def true_demand(conn, sku_id: str, day: str, rates=None):
    """返回 (实际销量, 缺货小时, 真实需求估计)。"""
    sold = conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM sales WHERE sku_id=? AND day=?", (sku_id, day)
    ).fetchone()[0]

    row = conn.execute(
        "SELECT start_hour, end_hour FROM stockout_mark WHERE sku_id=? AND day=?",
        (sku_id, day),
    ).fetchone()
    miss = missing_hours(*row) if row else 0

    if rates is None:
        rates = hourly_rates(conn)
    wd = conn.execute("SELECT weekday FROM sales WHERE sku_id=? AND day=? LIMIT 1",
                      (sku_id, day)).fetchone()
    rate = rates.get((sku_id, wd[0]), 0.0) if wd else 0.0
    return sold, miss, sold + miss * rate
