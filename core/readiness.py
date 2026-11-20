# -*- coding: utf-8 -*-
"""数据就绪度：判断这家的历史够不够跑预测；不够时系统自己降级，而不是硬算。

三个门槛都出自现有代码，不是拍脑袋定的：
  21 天  3 个同星期几 —— pipeline.forecast 的 confidence 在这里由 low 转 normal
  14 天  2 个完整周 —— 周内系数可估，均值勉强能用
  28 天  4 个完整周 —— 每个星期几各有 4 个样本，区间与三档才有统计意义

预测、区间、三档的算法一行都不改；这里只回答「现在能不能用、还差多少天」。
"""
from __future__ import annotations

import pandas as pd

from . import connect

MIN_TRANSIT = 14
MIN_FULL = 28
MIN_CONF = 21

MODE = {
    "cold": ("冷启动", "记录为主：先把单品卖了多少记下来，订货仍按老经验。"),
    "transit": ("过渡", "可以算均值和周内规律，区间偏宽，建议当参考而非依据。"),
    "full": ("完整", "预测、区间、三档损失都能用。"),
}


def per_sku_days(conn=None) -> pd.DataFrame:
    """每个单品有多少个「有销售的日子」。"""
    conn = conn or connect()
    return pd.read_sql_query(
        "SELECT sku_id, COUNT(DISTINCT day) AS days, "
        "MIN(day) AS first_day, MAX(day) AS last_day "
        "FROM sales GROUP BY sku_id ORDER BY days", conn)


def readiness(conn=None) -> dict:
    """整体判断：这一家现在处在哪一档，还差多少天到完整。"""
    conn = conn or connect()
    df = per_sku_days(conn)
    span = conn.execute("SELECT COUNT(DISTINCT day) FROM sales").fetchone()[0]
    span = int(span or 0)

    if df.empty or span == 0:
        return {"mode": "cold", "label": MODE["cold"][0], "days": 0,
                "median": 0, "weak": [], "need": MIN_FULL,
                "advice": "还没有销售记录。" + MODE["cold"][1]}

    median = float(df["days"].median())
    if median < MIN_TRANSIT:
        mode = "cold"
    elif median < MIN_FULL:
        mode = "transit"
    else:
        mode = "full"

    weak = [r["sku_id"] for _, r in df.iterrows() if r["days"] < MIN_TRANSIT]
    need = max(0, MIN_FULL - int(median))

    if mode == "full":
        advice = MODE["full"][1]
    elif mode == "transit":
        advice = MODE["transit"][1] + f"再有 {need} 天到完整档。"
    else:
        advice = MODE["cold"][1] + f"再有 {max(0, MIN_TRANSIT - int(median))} 天可进过渡档。"

    return {"mode": mode, "label": MODE[mode][0], "days": span,
            "median": int(median), "weak": weak, "need": need,
            "advice": advice}


def sku_mode(sku_id: str, conn=None) -> tuple[str, int]:
    """单个单品的档位与可用天数。数据太少的单品由调用方决定是否退回经验法。"""
    conn = conn or connect()
    n = conn.execute(
        "SELECT COUNT(DISTINCT day) FROM sales WHERE sku_id=?", (sku_id,)).fetchone()[0]
    n = int(n or 0)
    if n < MIN_TRANSIT:
        return "cold", n
    if n < MIN_FULL:
        return "transit", n
    return "full", n
