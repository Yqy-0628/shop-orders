# -*- coding: utf-8 -*-
"""规则引擎：决定「今天要不要叫人、叫哪几件」。

两类规则：
  数据异常 —— 数据本身有问题，必须先处理（否则预测全错）
  待决事项 —— 数据没问题，但这一件需要老板拍板

每条规则都能用一句人话解释，没有黑箱。
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from . import connect, pipeline

CLOSE_H = 21
RECENT = 28          # 「近一个月」的窗口
HIGH_K = 1.20        # 预测高于近期均值 20% → 叫人
LOW_K = 0.80
STREAK = 3           # 连续售罄天数阈值
WASTE_DAYS = 7


def _last_day(conn) -> str | None:
    r = conn.execute("SELECT MAX(day) FROM sales").fetchone()
    return r[0] if r else None


# ---------------------------------------------------------------- 数据异常
def data_issues(day: str | None = None) -> list[dict]:
    conn = connect()
    last = day or _last_day(conn)
    if not last:
        return [{"code": "no_data", "sku_id": "", "name": "",
                 "message": "尚无销售记录",
                 "fix_hint": "补录一日销量", "severity": "block"}]

    out = []
    skus = [dict(r) for r in conn.execute("SELECT sku_id, name FROM sku")]

    # ① 当天完全没有销售记录
    n = conn.execute("SELECT COUNT(*) FROM sales WHERE day=?", (last,)).fetchone()[0]
    if n == 0:
        out.append({"code": "no_data", "sku_id": "", "name": "",
                    "message": f"{last} 无销售记录",
                    "fix_hint": "确认是否停业；营业中请补录",
                    "severity": "block"})
        return out

    # ② 售罄时刻不合法（≥ 打烊时间）
    for r in conn.execute(
            "SELECT sku_id, start_hour FROM stockout_mark WHERE day=? AND start_hour>=?",
            (last, CLOSE_H)):
        nm = next((s["name"] for s in skus if s["sku_id"] == r["sku_id"]), r["sku_id"])
        out.append({"code": "soldout_after_close", "sku_id": r["sku_id"], "name": nm,
                    "message": f"售罄时刻 {r['start_hour']}:00 晚于打烊时间",
                    "fix_hint": "改为打烊前时刻，或删除该记录",
                    "severity": "warn"})

    # ③ 库存耗尽了、却没有售罄标记 —— 很可能忘了点
    for r in conn.execute(
            "SELECT sku_id, SUM(qty) q FROM sales WHERE day=? GROUP BY sku_id", (last,)):
        so = conn.execute(
            "SELECT 1 FROM stockout_mark WHERE sku_id=? AND day=?",
            (r["sku_id"], last)).fetchone()
        if so:
            continue

        flow = conn.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN type='入库' THEN qty ELSE 0 END),0) AS inflow,
                 COALESCE(SUM(CASE WHEN type='报损' THEN -qty ELSE 0 END),0) AS waste
               FROM stock_move WHERE sku_id=? AND day=?""",
            (r["sku_id"], last)).fetchone()
        left = flow["inflow"] - r["q"] - flow["waste"]
        if left > 0:          # 还有剩货，卖得多是正常的，不算异常
            continue

        hist = conn.execute(
            """SELECT AVG(q) FROM (SELECT day, SUM(qty) q FROM sales
               WHERE sku_id=? AND day<? AND day>=date(?, '-28 day') GROUP BY day)""",
            (r["sku_id"], last, last)).fetchone()[0]
        if hist and r["q"] >= hist * 1.15:
            nm = next((s["name"] for s in skus if s["sku_id"] == r["sku_id"]), r["sku_id"])
            out.append({"code": "missing_soldout", "sku_id": r["sku_id"], "name": nm,
                        "message": f"当日余量 {left} 但未记录售罄",
                        "fix_hint": "在收银页补记售罄时刻",
                        "severity": "warn"})
    return out


# ---------------------------------------------------------------- 待决事项
def today_tasks(day: str | None = None, limit: int = 3) -> list[dict]:
    conn = connect()
    target = day or _next_day(conn)
    wd = dt.date.fromisoformat(target).weekday()
    skus = [dict(r) for r in conn.execute(
        "SELECT sku_id, name FROM sku ORDER BY sku_id")]

    tasks = []
    for s in skus:
        sid = s["sku_id"]
        df = pipeline.load_daily(conn, sid)
        if len(df) < 14:
            continue
        df = pipeline.fill_demand(df, pipeline.hourly_rate(conn, sid))
        fc = pipeline.forecast(df, wd)
        recent = float(df["demand"].tail(RECENT).mean())
        if recent <= 0:
            continue

        ratio = fc["value"] / recent
        streak = _soldout_streak(df)
        waste = _waste_rate(conn, sid, target)

        if ratio >= HIGH_K:
            tasks.append(dict(
                sku_id=sid, name=s["name"], type="high",
                title=f"次日预计 {fc['value']} 件，高于近月均值 {(ratio-1)*100:.0f}%",
                detail=f"近月日均 {recent:.0f}，区间 {fc['lo']}–{fc['hi']}",
                severity="warn", weight=abs(ratio - 1)))
        elif ratio <= LOW_K:
            tasks.append(dict(
                sku_id=sid, name=s["name"], type="low",
                title=f"次日预计 {fc['value']} 件，低于近月均值 {(1-ratio)*100:.0f}%",
                detail=f"近月日均 {recent:.0f}，建议评估减量",
                severity="info", weight=abs(ratio - 1)))

        if streak >= STREAK:
            tasks.append(dict(
                sku_id=sid, name=s["name"], type="soldout_streak",
                title=f"连续 {streak} 天售罄",
                detail="基准值偏低，建议上调订货量",
                severity="warn", weight=0.5 + streak * 0.1))

        if waste >= 0.10:
            tasks.append(dict(
                sku_id=sid, name=s["name"], type="waste_repeat",
                title=f"近 7 天报损率 {waste:.0%}",
                detail="基准值偏高，建议下调订货量",
                severity="warn", weight=waste))

    tasks.sort(key=lambda t: -t["weight"])
    return tasks[:limit]


def _next_day(conn) -> str:
    last = _last_day(conn)
    if not last:
        return dt.date.today().isoformat()
    return (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat()


def _soldout_streak(df: pd.DataFrame) -> int:
    n = 0
    for flag in reversed(df["soldout"].tolist()):
        if flag:
            n += 1
        else:
            break
    return n


def _waste_rate(conn, sku_id: str, upto: str) -> float:
    r = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN type='报损' THEN -qty ELSE 0 END),0) AS waste,
             COALESCE(SUM(CASE WHEN type='入库' THEN qty ELSE 0 END),0) AS inflow
           FROM stock_move
           WHERE sku_id=? AND day<=? AND day>=date(?, '-7 day')""",
        (sku_id, upto, upto)).fetchone()
    return (r["waste"] / r["inflow"]) if r["inflow"] else 0.0
