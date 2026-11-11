# -*- coding: utf-8 -*-
"""反事实重放：如果那天多订 N 件，会怎样。"""
from . import demand as D


def replay_day(conn, sku_id: str, day: str, extra_qty: int, rates=None):
    """返回 before/after 两组数，用于演示“如果那天多订 5 件”。"""
    sold, miss, true_d = D.true_demand(conn, sku_id, day, rates)
    sku = conn.execute(
        "SELECT name, price, cost FROM sku WHERE sku_id=?", (sku_id,)
    ).fetchone()
    margin = sku["price"] - sku["cost"]

    gap = max(0.0, true_d - sold)              # 当天没被满足的需求
    covered = min(gap, float(extra_qty))       # 多订 N 件能补回多少（件）
    new_sold = sold + covered

    return dict(
        sold_before=sold, sold_after=new_sold,
        gap=gap,
        recovered_qty=covered,
        recovered_value=covered * margin,
        lost_before=gap * margin,
        lost_after=(gap - covered) * margin,
        miss_hours_before=miss,
        margin=margin,
    )
