# -*- coding: utf-8 -*-
"""历史复盘：昨天错在哪、过去一个月「听系统的」和「实际」差多少。

两个都只用真实数据算，不造假记录：
  day_review  —— 用当天之前的数据预测当天，跟实际比
  scoreboard  —— 反事实回放：同样的需求，按实际订货 vs 按模型建议，报废和断货各是多少
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import connect, pipeline
from .rules import _last_day, _soldout_streak

CLOSE_H = 21


def _order_of(conn, sku_id: str, day: str) -> float:
    """那天实际订了多少（已到货的入库量）。"""
    v = conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM stock_move "
        "WHERE sku_id=? AND day=? AND type='入库' AND status='已到货'",
        (sku_id, day)).fetchone()[0]
    return float(v)


def day_review(day: str | None = None, limit: int = 8) -> list[dict]:
    """昨天每一件：预测多少、实际多少、算谁的错。"""
    conn = connect()
    last = _last_day(conn)
    if not last:
        return []
    target = day or last
    wd = dt.date.fromisoformat(target).weekday()

    out = []
    for s in conn.execute("SELECT sku_id, name FROM sku ORDER BY sku_id"):
        df = pipeline.load_daily(conn, s["sku_id"])
        if len(df) < 14:
            continue
        idx = df.index[df["day"] == target]
        if len(idx) == 0:
            continue
        i = int(idx[0])
        hist = df.iloc[:i]
        if len(hist) < 14:
            continue

        f = pipeline.forecast(
            pipeline.fill_demand(hist, pipeline.hourly_rate(conn, s["sku_id"])), wd)
        actual = float(df.iloc[i]["sold"])
        err = (actual - f["value"]) / max(f["value"], 1)

        kind = "model"
        if df.iloc[i]["soldout"]:
            kind = "data"        # 卖光了，销量不是真实需求，错在数据
        elif abs(err) <= 0.10:
            kind = "none"
        elif _soldout_streak(df.iloc[:i + 1]) >= 2 and actual > f["hi"]:
            kind = "data"

        out.append({
            "sku_id": s["sku_id"], "name": s["name"],
            "predicted": f["value"], "actual": round(actual),
            "kind": kind,
        })
        if len(out) >= limit:
            break
    return out


def scoreboard(days: int = 30) -> dict:
    """反事实回放：同样的需求，两种订法各亏多少。

    返回 {"days",
          "actual": {"waste", "stockout_days"},  实际怎么订
          "model":  {"waste", "stockout_days"},  按建议订
          "delta_waste", "delta_stockout"}
    """
    conn = connect()
    last = _last_day(conn)
    empty = {"days": 0,
             "actual": {"waste": 0, "stockout_days": 0},
             "model": {"waste": 0, "stockout_days": 0},
             "delta_waste": 0, "delta_stockout": 0,
             "money_actual": 0, "money_model": 0, "money_saved": 0}
    if not last:
        return empty

    end = dt.date.fromisoformat(last)
    start = (end - dt.timedelta(days=days - 1)).isoformat()

    aw = mw = 0.0
    au = mu = 0.0
    money_a = money_m = 0.0
    ast = mst = 0

    for s in conn.execute("SELECT sku_id, cost, price, salvage FROM sku ORDER BY sku_id"):
        sid = s["sku_id"]
        cost, price, salvage = s["cost"], s["price"], s["salvage"]
        df = pipeline.load_daily(conn, sid)
        if len(df) < 14:
            continue
        df = pipeline.fill_demand(df, pipeline.hourly_rate(conn, sid))

        for i in range(len(df)):
            d = df.iloc[i]["day"]
            if d < start or d > last:
                continue
            hist = df.iloc[:i]
            if len(hist) < 14:
                continue
            wd = int(df.iloc[i]["weekday"])
            pred = pipeline.forecast(hist, wd)["value"]
            actual_order = _order_of(conn, sid, d)
            demand = float(df.iloc[i]["demand"])
            if actual_order <= 0 or pred <= 0:
                continue

            cu = float(price) - float(cost)        # 断货一件少赚的
            co = float(cost) - float(salvage)      # 报废一件净亏的
            aw += max(0.0, actual_order - demand)
            mw += max(0.0, pred - demand)
            ast += 1 if demand > actual_order else 0
            mst += 1 if demand > pred else 0
            au += max(0.0, demand - actual_order)
            mu += max(0.0, demand - pred)
            money_a += max(0.0, actual_order - demand) * co + max(0.0, demand - actual_order) * cu
            money_m += max(0.0, pred - demand) * co + max(0.0, demand - pred) * cu

    n = max(1, days)
    return {
        "days": days,
        "actual": {"waste": round(aw, 0), "stockout_days": ast},
        "model": {"waste": round(mw, 0), "stockout_days": mst},
        "delta_waste": round(aw - mw, 0),
        "delta_stockout": ast - mst,
        "money_actual": round(money_a, 0),
        "money_model": round(money_m, 0),
        "money_saved": round(money_a - money_m, 0),
    }
