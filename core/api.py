# -*- coding: utf-8 -*-
"""接口契约层。

规则（两个人都要守）：
  1. pages/ 只准 import 这个文件，不准直接碰 sqlite、不准 import core 里其他模块。
  2. 这里返回的全是普通 dict / list，不是 sqlite3.Row —— 免得页面层依赖数据库细节。
  3. 改函数签名之前，必须在群里说一句。

现在的状态：签名已定死，函数体是「假数据」。
等 core 里的真算法接好，只换实现，不改签名。
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta

from . import connect

DEMO_TODAY = "2026-11-15"


def _today(d=None) -> str:
    return d or DEMO_TODAY


def _skus(conn):
    return [dict(r) for r in conn.execute(
        "SELECT sku_id, name, category, cost, price, salvage, mu, sigma, "
        "shelf_life_days FROM sku ORDER BY sku_id")]


# ---------------------------------------------------------------- 数据异常
def data_issues(day: str | None = None) -> list[dict]:
    """12 条分支里属于「数据脏」的那几条。

    返回 [{"code", "sku_id", "name", "message", "fix_hint", "severity"}]
    severity: "block"（必须处理才能继续） | "warn"（提示即可）
    """
    day = _today(day)
    conn = connect()
    rows = _skus(conn)
    out = []

    # 示例规则：昨天有销售、但没有任何售罄标记，且库存为 0 —— 很可能忘了点
    # （真实现放在 core/rules.py，这里只保证形状稳定）
    if rows:
        s = rows[0]
        out.append({
            "code": "missing_soldout",
            "sku_id": s["sku_id"], "name": s["name"],
            "message": "昨天有销量，但没记售罄",
            "fix_hint": "点一下「补录售罄」，或确认当天确实没卖完",
            "severity": "warn",
        })
    return out


# ---------------------------------------------------------------- 今日待决
def today_tasks(day: str | None = None) -> list[dict]:
    """今天需要老板拍板的几件事。

    返回 [{"sku_id", "name", "type", "title", "detail", "severity"}]
    type: high / low / soldout_streak / waste_repeat
    """
    day = _today(day)
    conn = connect()
    rows = _skus(conn)
    out = []
    for s, t, title, detail in zip(
        rows[:3],
        ["high", "soldout_streak", "low"],
        ["明天可能偏高", "连续卖光", "明天可能偏低"],
        ["比平时高 25%，因为周六 + 考试周",
         "连续 3 天售罄，基准可能偏低",
         "比平时低 20%，因为最近在回落"],
    ):
        out.append({
            "sku_id": s["sku_id"], "name": s["name"], "type": t,
            "title": title, "detail": detail, "severity": "warn",
        })
    return out


# ---------------------------------------------------------------- 预测
def predict(sku_id: str, day: str | None = None) -> dict:
    """单品的次日预测。

    返回 {
        "sku_id", "name", "day",
        "value": 33, "lo": 24, "hi": 38, "level": 0.90,
        "explain": [{"label": "基准", "value": 26}, {"label": "星期", "value": "×1.28"}, ...],
        "confidence": "normal" | "low"
    }
    """
    day = _today(day)
    conn = connect()
    s = conn.execute("SELECT * FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if s is None:
        raise KeyError(f"没有这个商品: {sku_id}")
    value = round(float(s["mu"]))
    return {
        "sku_id": sku_id, "name": s["name"], "day": day,
        "value": value,
        "lo": max(1, round(value * 0.72)),
        "hi": round(value * 1.18),
        "level": 0.90,
        "explain": [
            {"label": "基准", "value": round(float(s["mu"]))},
            {"label": "星期", "value": "×1.28"},
            {"label": "趋势", "value": "×1.02"},
            {"label": "特殊日", "value": "无"},
        ],
        "confidence": "normal",
    }


# ---------------------------------------------------------------- 三档建议
def suggest(sku_id: str, day: str | None = None) -> dict:
    """把预测换成三档建议，每档带代价。

    返回 {"sku_id", "day", "tiers": [{"key","name","qty","waste","stockout"}],
          "recommend": "normal"}
    """
    p = predict(sku_id, day)
    v = p["value"]
    return {
        "sku_id": sku_id, "day": p["day"],
        "tiers": [
            {"key": "save",   "name": "省着订", "qty": round(v * 0.90),
             "waste": 1, "stockout": 0.35},
            {"key": "normal", "name": "稳妥订", "qty": round(v * 1.03),
             "waste": 3, "stockout": 0.12},
            {"key": "safe",   "name": "保险订", "qty": round(v * 1.15),
             "waste": 6, "stockout": 0.04},
        ],
        "recommend": "normal",
    }


# ---------------------------------------------------------------- 记录
def record_decision(sku_id: str, qty: int, reason: str | None = None,
                    day: str | None = None, user: str = "boss") -> dict:
    """老板拍板。reason 是手改时的原因（天气/活动/经验/其他），没改可以留空。"""
    day = _today(day)
    ts = datetime.now().isoformat(timespec="seconds")
    return {"ok": True, "sku_id": sku_id, "day": day, "qty": qty,
            "reason": reason or "", "ts": ts}


def record_arrival(sku_id: str, qty: int, day: str | None = None) -> dict:
    """到货登记。qty 是实收数量，跟订单不一致时由调用方传差异备注。"""
    return {"ok": True, "sku_id": sku_id, "day": _today(day), "qty": qty}


def record_soldout(sku_id: str, hour: int, day: str | None = None) -> dict:
    """卖光了，点一下。hour 用 24 小时制。"""
    return {"ok": True, "sku_id": sku_id, "day": _today(day), "hour": hour}


# ---------------------------------------------------------------- 记分板
def scoreboard(days: int = 30) -> dict:
    """人和模型的对照。

    返回 {"days", "follow": {"days", "waste"}, "ignore": {"days", "waste"}, "delta"}
    delta 是「没听系统」比「听系统」每天多扔几个。
    """
    return {
        "days": days,
        "follow": {"days": 12, "waste": 2.1},
        "ignore": {"days": 18, "waste": 5.4},
        "delta": 3.3,
    }


# ---------------------------------------------------------------- 复盘
def day_review(day: str | None = None) -> list[dict]:
    """次日的复盘清单：昨天每一件，预测多少、实际多少、算谁的错。

    返回 [{"sku_id","name","predicted","actual","kind"}]  kind: model/data/human/none
    """
    day = _today(day)
    conn = connect()
    out = []
    for s in _skus(conn)[:4]:
        out.append({
            "sku_id": s["sku_id"], "name": s["name"],
            "predicted": round(float(s["mu"])),
            "actual": round(float(s["mu"]) * 1.12),
            "kind": "model",
        })
    return out


# ---------------------------------------------------------------- 自动下单
def auto_lines(day: str | None = None) -> list[dict]:
    """不需要老板拍板、按常规量自动下的品类。"""
    day = _today(day)
    conn = connect()
    return [{"sku_id": s["sku_id"], "name": s["name"],
             "qty": round(float(s["mu"]))} for s in _skus(conn)[3:]]
