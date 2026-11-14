# -*- coding: utf-8 -*-
"""预测管道：从数据库读到「预测 + 区间 + 三档」，全流程。

三个关键决策：
  1. 基准用「同星期几的补齐值均值」，不再单乘星期系数（否则重复计算）
  2. 趋势裁剪在 0.8–1.25，防一次促销把预测拉飞
  3. 区间用历史变异系数，不假设正态；三档用历史样本回放，不假设分布
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import connect

OPEN_H, CLOSE_H = 9, 21
HORIZON = CLOSE_H - OPEN_H
TREND_WIN = 14


def load_daily(conn, sku_id: str) -> pd.DataFrame:
    """每个 SKU 的日序列：销量 + 当天是否售罄、几点售罄。"""
    sql = """
        SELECT s.day,
               s.weekday,
               SUM(s.qty) AS sold,
               MIN(m.start_hour) AS so_hour
        FROM sales s
        LEFT JOIN stockout_mark m
               ON m.sku_id = s.sku_id AND m.day = s.day
        WHERE s.sku_id = ?
        GROUP BY s.day
        ORDER BY s.day
    """
    df = pd.read_sql_query(sql, conn, params=(sku_id,))
    if df.empty:
        return df
    df["so_hour"] = df["so_hour"].fillna(CLOSE_H)
    df["soldout"] = df["so_hour"] < CLOSE_H
    return df


def hourly_rate(conn, sku_id: str) -> float:
    """每小时销量率：只用「当天没售罄」的日子，因为只有那些天销量 = 需求。"""
    sql = """
        SELECT AVG(x.qty) FROM (
            SELECT SUM(s.qty) * 1.0 / ? AS qty
            FROM sales s
            WHERE s.sku_id = ?
              AND s.day NOT IN (SELECT day FROM stockout_mark WHERE sku_id = ?)
            GROUP BY s.day
        ) x
    """
    v = pd.read_sql_query(sql, conn, params=(HORIZON, sku_id, sku_id)).iloc[0, 0]
    return float(v) if v is not None and not pd.isna(v) else 0.0


def fill_demand(df: pd.DataFrame, rate: float) -> pd.DataFrame:
    """把售罄那天的需求补回来。没售罄的日子，销量就是需求。"""
    df = df.copy()
    missing_h = np.where(df["soldout"], CLOSE_H - df["so_hour"], 0)
    df["missing_h"] = missing_h
    df["demand"] = df["sold"] + missing_h * rate
    return df


def trend_ratio(demand: np.ndarray, win: int = TREND_WIN) -> float:
    """近 win 天 ÷ 前 win 天，裁剪在 0.8–1.25。"""
    if len(demand) < 2 * win:
        return 1.0
    a = demand[-win:].sum()
    b = demand[-2 * win:-win].sum()
    if b <= 0:
        return 1.0
    return float(np.clip(a / b, 0.8, 1.25))


def forecast(df: pd.DataFrame, weekday: int, k: int = 8) -> dict:
    """给定「下一个星期几」，预测它的需求。"""
    hist = df[df["weekday"] == weekday]
    if hist.empty:
        hist = df
    recent = hist.tail(k)
    base = float(recent["demand"].mean())

    tr = trend_ratio(df["demand"].values)
    pred = base * tr

    tail = df["demand"].tail(28)
    cv = float(tail.std() / tail.mean()) if tail.mean() > 0 else 0.3
    cv = float(np.clip(cv, 0.05, 0.8))
    half = 1.28 * cv

    return {
        "value": round(pred),
        "lo": max(1, round(pred * (1 - half))),
        "hi": round(pred * (1 + half)),
        "level": 0.90,
        "explain": [
            {"label": "基准", "value": f"{base:.1f}（最近 {len(recent)} 个同星期几）"},
            {"label": "近期日均", "value": f"{df['demand'].tail(28).mean():.1f}（全周）"},
            {"label": "趋势", "value": f"×{tr:.2f}"},
            {"label": "波动", "value": f"CV {cv*100:.0f}%"},
        ],
        "confidence": "low" if len(hist) < 3 else "normal",
    }


def tiers(df: pd.DataFrame, weekday: int) -> list[dict]:
    """三档建议：用历史样本回放算断货概率和预计报废。"""
    pred = forecast(df, weekday)
    samples = df["demand"].tail(56).values
    if len(samples) < 10:
        samples = df["demand"].values
    qs = np.quantile(samples, [0.55, 0.80, 0.92])

    out = []
    for key, name, q in zip(("save", "normal", "safe"),
                            ("省着订", "稳妥订", "保险订"), qs):
        Q = max(1, round(float(q)))
        out.append({
            "key": key, "name": name, "qty": Q,
            "stockout": round(float((samples > Q).mean()), 2),
            "waste": round(float(np.maximum(0, Q - samples).mean()), 1),
        })
    return out


def predict_sku(sku_id: str, weekday: int, conn=None) -> dict | None:
    conn = conn or connect()
    df = load_daily(conn, sku_id)
    if df.empty:
        return None
    rate = hourly_rate(conn, sku_id)
    df = fill_demand(df, rate)
    return forecast(df, weekday)


def suggest_sku(sku_id: str, weekday: int, conn=None) -> dict | None:
    conn = conn or connect()
    df = load_daily(conn, sku_id)
    if df.empty:
        return None
    df = fill_demand(df, hourly_rate(conn, sku_id))
    return {"tiers": tiers(df, weekday), "recommend": "normal"}
