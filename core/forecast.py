# -*- coding: utf-8 -*-
"""四个预测方法 + 共形区间。纯 numpy/pandas，不依赖 scipy。

0  同星期均值（基线）
1  Holt 线性趋势（指数平滑）
2  分层池化：单品预测向「品类预测 × 占比」收缩
3  共形区间：用历史残差的分位数给区间，不假设分布
"""
import numpy as np
import pandas as pd


def same_weekday_mean(vals: np.ndarray, weekday: np.ndarray, t: int, k: int = 4) -> float:
    """最近 k 个同星期的观测均值。"""
    if t == 0:
        return 0.0
    wd = weekday[t]
    idx = np.where(weekday[:t] == wd)[0]
    if len(idx) == 0:
        return float(vals[:t].mean())
    return float(vals[idx[-k:]].mean())


def holt(vals: np.ndarray, t: int, alpha: float = 0.35, beta: float = 0.12) -> float:
    """Holt 线性趋势，一步向前。"""
    y = vals[:t].astype(float)
    if len(y) < 3:
        return float(y.mean()) if len(y) else 0.0
    level, trend = y[0], y[1] - y[0]
    for v in y[1:]:
        prev = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
    return float(max(0.0, level + trend))


def shrink_toward(own: float, anchor: float, n: int, k: float = 6.0) -> float:
    """数据越少，越相信 anchor（品类推断）；n 是已有观测数。"""
    w = n / (n + k)
    return float(w * own + (1 - w) * anchor)


def conformal_quantile(residuals: np.ndarray, level: float = 0.90) -> float:
    """共形预测的半宽：残差绝对值的 level 分位数。"""
    if len(residuals) == 0:
        return 0.0
    return float(np.quantile(np.abs(residuals), level))


def mape(y_true: np.ndarray, y_pred: np.ndarray, floor: float = 3.0) -> float:
    """只算真实值 >= floor 的天，避免小分母爆炸。"""
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    m = y_true >= floor
    return float(np.mean(np.abs(y_true[m] - y_pred[m]) / y_true[m]) * 100)


def bias(y_true: np.ndarray, y_pred: np.ndarray, floor: float = 3.0) -> float:
    """正数＝系统性高估。"""
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    m = y_true >= floor
    return float(np.mean((y_pred[m] - y_true[m]) / np.maximum(y_true[m], 1e-9)) * 100)
