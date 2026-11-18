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

import json

from . import connect, metrics, pipeline, review, rules


def _today(d=None) -> str:
    return d or metrics.biz_day()


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
    # 数据异常检查的是「最后一个有数据的日子」，不是预测目标日
    return rules.data_issues(day)


# ---------------------------------------------------------------- 今日待决
def today_tasks(day: str | None = None) -> list[dict]:
    """今天需要老板拍板的几件事。

    返回 [{"sku_id", "name", "type", "title", "detail", "severity"}]
    type: high / low / soldout_streak / waste_repeat
    """
    day = _today(day)
    return rules.today_tasks(day)


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
    s = conn.execute("SELECT sku_id, name FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if s is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    wd = datetime.strptime(day, "%Y-%m-%d").weekday()
    r = pipeline.predict_sku(sku_id, wd, conn)
    if r is None:
        raise ValueError(f"{sku_id} 没有销售记录，无法预测")

    return {
        "sku_id": sku_id, "name": s["name"], "day": day,
        "value": r["value"], "lo": r["lo"], "hi": r["hi"],
        "level": r["level"], "explain": r["explain"],
        "confidence": r["confidence"],
    }


# ---------------------------------------------------------------- 三档建议
def suggest(sku_id: str, day: str | None = None) -> dict:
    """把预测换成三档建议，每档带代价。

    返回 {"sku_id", "day", "tiers": [{"key","name","qty","waste","stockout"}],
          "recommend": "normal"}
    """
    day = _today(day)
    wd = datetime.strptime(day, "%Y-%m-%d").weekday()
    conn = connect()
    r = pipeline.suggest_sku(sku_id, wd, conn)
    if r is None:
        raise ValueError(f"{sku_id} 没有销售记录，无法给建议")
    return {"sku_id": sku_id, "day": day,
            "tiers": r["tiers"], "recommend": r["recommend"]}


# ---------------------------------------------------------------- 记录
def record_decision(sku_id: str, qty: int, reason: str | None = None,
                    day: str | None = None, user: str = "boss") -> dict:
    """老板拍板。reason 是手改时的原因（天气/活动/经验/其他），没改可以留空。

    落两处：decision_log 记「谁、建议多少、实际多少、为什么改」；
    stock_move 记一张「在途」的入库单，第二天到货时转成已到货。
    """
    day = _today(day)
    conn = connect()
    ts = datetime.now().isoformat(timespec="seconds")
    row = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    try:
        suggested = predict(sku_id, day)["value"]
    except Exception:
        suggested = qty

    # 同一天重复下单：覆盖上一条在途
    conn.execute(
        "DELETE FROM stock_move WHERE sku_id=? AND day=? AND status='在途'",
        (sku_id, day))
    conn.execute(
        "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
        "VALUES (?,?,'入库',?,?,'在途')",
        (sku_id, day, qty, row["cost"]))
    conn.execute(
        "INSERT INTO decision_log (ts, username, sku_id, params_json, q_star, "
        "adopted_qty, adopted) VALUES (?,?,?,?,?,?,?)",
        (ts, user, sku_id,
         json.dumps({"reason": reason or "", "target_day": day}, ensure_ascii=False),
         suggested, qty, 0 if reason else 1))
    conn.commit()

    return {"ok": True, "sku_id": sku_id, "day": day, "qty": qty,
            "reason": reason or "", "ts": ts, "suggested": suggested}


def record_arrival(sku_id: str, qty: int, day: str | None = None) -> dict:
    """到货登记。把同一天的在途单转成已到货，数量以实收为准。"""
    day = _today(day)
    conn = connect()
    row = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    conn.execute(
        "DELETE FROM stock_move WHERE sku_id=? AND day=? AND status='在途'",
        (sku_id, day))
    conn.execute(
        "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
        "VALUES (?,?,'入库',?,?,'已到货')",
        (sku_id, day, qty, row["cost"]))
    conn.commit()
    return {"ok": True, "sku_id": sku_id, "day": day, "qty": qty}


def record_waste(sku_id: str, qty: int, day: str | None = None) -> dict:
    """报损登记。qty 是报废件数（正数），存进库时转成负数。"""
    day = _today(day)
    conn = connect()
    row = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    conn.execute(
        "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
        "VALUES (?,?,'报损',?,?,'已到货')",
        (sku_id, day, -abs(qty), row["cost"]))
    conn.commit()
    return {"ok": True, "sku_id": sku_id, "day": day, "qty": -abs(qty)}


def record_soldout(sku_id: str, hour: int, day: str | None = None) -> dict:
    """卖光了，点一下。hour 用 24 小时制。同一天重复点会覆盖。"""
    day = _today(day)
    conn = connect()
    conn.execute("DELETE FROM stockout_mark WHERE sku_id=? AND day=?", (sku_id, day))
    conn.execute(
        "INSERT INTO stockout_mark (sku_id, day, start_hour, end_hour) VALUES (?,?,?,?)",
        (sku_id, day, int(hour), 21))
    conn.commit()
    return {"ok": True, "sku_id": sku_id, "day": day, "hour": hour}


def record_sale(sku_id: str, qty: int, hour: int | None = None,
                day: str | None = None) -> dict:
    """记一笔销量。一天可以记多次，累加进 sales。

    返回该品类当天的累计销量，页面直接显示，免得重复录。
    """
    day = _today(day)
    conn = connect()
    row = conn.execute("SELECT price FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    h = max(9, min(21, int(hour or 15)))
    wd = datetime.strptime(day, "%Y-%m-%d").weekday()
    conn.execute(
        "INSERT INTO sales (sku_id, day, hour, weekday, qty, unit_price) "
        "VALUES (?,?,?,?,?,?)",
        (sku_id, day, h, wd, int(qty), row["price"]))
    conn.commit()

    total = conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM sales WHERE sku_id=? AND day=?",
        (sku_id, day)).fetchone()[0]
    return {"ok": True, "sku_id": sku_id, "day": day,
            "qty": int(qty), "total": int(total)}


def record_count(sku_id: str, real_qty: int, day: str | None = None) -> dict:
    """盘点：把账面累计结余调成实盘数，差额写成一条「盘点」流水。"""
    day = _today(day)
    conn = connect()
    row = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    book = 0
    for r in metrics.stock_rows(conn, day):
        if r["sku_id"] == sku_id:
            book = r["qty"]
            break
    diff = int(real_qty) - int(book)

    if diff != 0:
        conn.execute(
            "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
            "VALUES (?,?,'盘点',?,?,'已到货')",
            (sku_id, day, diff, row["cost"]))
        conn.commit()

    return {"ok": True, "sku_id": sku_id, "day": day,
            "book": int(book), "real": int(real_qty), "diff": diff}


# ---------------------------------------------------------------- 记分板
def scoreboard(days: int = 30) -> dict:
    """反事实回放：同样的需求，按实际订货 vs 按建议订货，各亏多少钱。"""
    return review.scoreboard(days)


# ---------------------------------------------------------------- 复盘
def day_review(day: str | None = None) -> list[dict]:
    """次日的复盘清单：昨天每一件，预测多少、实际多少、算谁的错。

    返回 [{"sku_id","name","predicted","actual","kind"}]  kind: model/data/human/none
    """
    return review.day_review(day)


# ---------------------------------------------------------------- 自动下单
def auto_lines(day: str | None = None) -> list[dict]:
    """不需要老板拍板、按常规量自动下的品类。"""
    day = _today(day)
    conn = connect()
    return [{"sku_id": s["sku_id"], "name": s["name"],
             "qty": round(float(s["mu"]))} for s in _skus(conn)[3:]]
