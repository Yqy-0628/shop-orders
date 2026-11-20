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
from .order import costs, q_star, service_level

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


def tiers(df: pd.DataFrame, weekday: int,
          unit: tuple | None = None) -> list[dict]:
    """三档建议：围着预测值上下浮动，代价用历史样本实测（不假设分布）。

    档位倍数 0.90 / 1.00 / 1.25；断货概率、报废量、断货量都从历史样本里数出来。
    unit=(进价, 售价, 残值) 时，额外把两笔损失折成「元」。
    """
    base = forecast(df, weekday)["value"]
    samples = df[df["weekday"] == weekday]["demand"].values
    if len(samples) < 8:
        samples = df["demand"].tail(56).values
    if len(samples) < 10:
        samples = df["demand"].values

    cost = price = salvage = None
    if unit:
        cost, price, salvage = unit

    out = []
    for key, name, mult in (("save", "少订一成", 0.90),
                            ("normal", "按预测订", 1.00),
                            ("safe", "多订两成", 1.25)):
        Q = max(1, round(base * mult))
        waste = float(np.maximum(0, Q - samples).mean())
        short = float(np.maximum(0, samples - Q).mean())
        item = {
            "key": key, "name": name, "qty": Q,
            "stockout": round(float((samples > Q).mean()), 2),
            "waste": round(waste, 1),
            "short": round(short, 1),
        }
        if unit:
            item["waste_cost"] = round(waste * (cost - salvage), 1)
            item["short_cost"] = round(short * (price - cost), 1)
            item["cost_total"] = round(item["waste_cost"] + item["short_cost"], 1)
        out.append(item)
    return out


def predict_sku(sku_id: str, weekday: int, conn=None) -> dict | None:
    conn = conn or connect()
    df = load_daily(conn, sku_id)
    if df.empty:
        return None
    rate = hourly_rate(conn, sku_id)
    df = fill_demand(df, rate)
    return forecast(df, weekday)


def optimum(df: pd.DataFrame, weekday: int, unit: tuple) -> dict:
    """报童最优量：Q* = μ + z(临界比) × σ。

    μ 必须和预测用同一个基准——同星期几的补齐均值再乘趋势，
    否则周一按全周平均订、周五也按全周平均订，两个都不对。
    σ 优先用同星期几样本的标准差，样本不足四周时退回全周尾部。
    """
    f = forecast(df, weekday)
    mu = float(f["value"])

    hist = df[df["weekday"] == weekday]
    if len(hist) >= 4:
        sigma = float(hist["demand"].tail(8).std())
    else:
        sigma = float(df["demand"].tail(28).std())
    sigma = max(0.0, sigma)

    cost, price, salvage = unit
    cr = service_level(cost, price, salvage)
    cu, co = costs(cost, price, salvage)
    return {"qty": max(1, round(q_star(mu, sigma, cost, price, salvage))),
            "mu": round(mu, 1), "sigma": round(sigma, 1),
            "cr": round(cr, 3), "cu": round(cu, 2), "co": round(co, 2)}


def suggest_sku(sku_id: str, weekday: int, conn=None) -> dict | None:
    conn = conn or connect()
    df = load_daily(conn, sku_id)
    if df.empty:
        return None
    df = fill_demand(df, hourly_rate(conn, sku_id))
    s = conn.execute("SELECT cost, price, salvage FROM sku WHERE sku_id=?",
                     (sku_id,)).fetchone()
    unit = (s["cost"], s["price"], s["salvage"]) if s else None
    out = {"tiers": tiers(df, weekday, unit), "recommend": "normal", "optimum": None}
    if unit:
        out["optimum"] = optimum(df, weekday, unit)
    return out
    return out
