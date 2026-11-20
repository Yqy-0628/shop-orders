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

from . import connect, metrics, pipeline, review, rules, importer


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
            "tiers": r["tiers"], "recommend": r["recommend"],
            "optimum": r.get("optimum")}


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


def record_arrival(sku_id: str, qty: int, day: str | None = None,
                   user: str = "boss") -> dict:
    """到货登记。把同一天的在途单转成已到货，数量以实收为准。

    顺带记一笔差异：昨天订的是 30、送来 25，差的那 5 件要让老板知道
    （少送、漏送、或者司机没送到位）。差异不为 0 时在 decision_log 留痕，
    params_json 里 kind='arrival_diff'，好和订货决策分开查。
    """
    day = _today(day)
    conn = connect()
    row = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    order = conn.execute(
        "SELECT COALESCE(SUM(qty),0) q, COUNT(*) n FROM stock_move "
        "WHERE sku_id=? AND day=? AND status='在途'", (sku_id, day)).fetchone()
    expected = int(order["q"]) if order["n"] else None
    diff = (qty - expected) if expected is not None else None

    conn.execute(
        "DELETE FROM stock_move WHERE sku_id=? AND day=? AND status='在途'",
        (sku_id, day))
    conn.execute(
        "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
        "VALUES (?,?,'入库',?,?,'已到货')",
        (sku_id, day, qty, row["cost"]))
    if diff:
        ts = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO decision_log (ts, username, sku_id, params_json, q_star, "
            "adopted_qty, adopted) VALUES (?,?,?,?,?,?,1)",
            (ts, user, sku_id,
             json.dumps({"kind": "arrival_diff", "expected": expected,
                         "received": qty, "day": day}, ensure_ascii=False),
             expected, qty))
    conn.commit()
    return {"ok": True, "sku_id": sku_id, "day": day, "qty": qty,
            "expected": expected, "diff": diff}


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


# ---------------------------------------------------------------- 商品档案维护
def update_sku(sku_id: str, cost: float | None = None, price: float | None = None,
               salvage: float | None = None, shelf_life_days: int | None = None) -> dict:
    """改商品档案里的价格与保质期。

    进价、售价、残值决定临界比，保质期决定报废口径，所以这四项必须能改，
    否则换一家店就得改数据库。校验规则：都为正数，售价高于进价，残值低于进价。
    """
    conn = connect()
    row = conn.execute(
        "SELECT cost, price, salvage, shelf_life_days FROM sku WHERE sku_id=?",
        (sku_id,)).fetchone()
    if row is None:
        raise KeyError(f"没有这个商品: {sku_id}")

    new = {
        "cost": float(cost if cost is not None else row["cost"]),
        "price": float(price if price is not None else row["price"]),
        "salvage": float(salvage if salvage is not None else row["salvage"]),
        "shelf_life_days": int(shelf_life_days if shelf_life_days is not None
                               else row["shelf_life_days"]),
    }
    if min(new["cost"], new["price"], new["salvage"]) <= 0:
        raise ValueError("进价、售价、残值都必须大于 0")
    if new["price"] <= new["cost"]:
        raise ValueError("售价必须高于进价，否则每卖一件都在亏")
    if new["salvage"] >= new["cost"]:
        raise ValueError("残值必须低于进价，否则多订一件反而赚钱")
    if not 1 <= new["shelf_life_days"] <= 7:
        raise ValueError("保质期只支持 1 至 7 天")

    conn.execute(
        "UPDATE sku SET cost=?, price=?, salvage=?, shelf_life_days=? WHERE sku_id=?",
        (new["cost"], new["price"], new["salvage"], new["shelf_life_days"], sku_id))
    conn.commit()
    return {"ok": True, "sku_id": sku_id, **new}


# ---------------------------------------------------------------- 数据导入
def import_read(raw: bytes) -> dict:
    """解一个 CSV 文件，顺手把字段猜出来。

    返回 {"headers", "rows", "guess"}；guess 是 {字段: 列号}，页面里可以改。
    """
    headers, rows = importer.read_bytes(raw)
    return {"headers": headers, "rows": rows, "guess": importer.guess_map(headers)}


def import_check(headers: list, rows: list, mapping: dict) -> dict:
    """逐行校验，不写库。返回 {"ok", "bad", "summary"}。"""
    ok, bad = importer.check(headers, rows, mapping)
    return {
        "ok": ok, "bad": bad,
        "summary": {
            "rows": len(ok) + len(bad), "ok": len(ok), "bad": len(bad),
            "units": sum(r["qty"] for r in ok),
            "days": sorted({r["day"] for r in ok}),
            "skus": len({r["sku_id"] for r in ok}),
        },
    }


def import_commit(ok_rows: list, replace_range: tuple | None = None) -> dict:
    """真正写库。replace_range=(起, 止) 时先清空该区间的销售再写。"""
    return importer.commit(ok_rows, replace_range)


def import_reconcile(day_from: str, day_to: str) -> dict:
    """对账：期初 + 进货 − 报损 = 余额，跟售出、售罄标记对不上的挑出来。"""
    return importer.reconcile(day_from, day_to)


def import_template() -> bytes:
    return importer.template_csv()


# ---------------------------------------------------------------- 收工日报
def day_close(day: str | None = None) -> dict:
    """一天的收工账：进多少、卖多少、报损多少、剩多少、几点卖光。

    短保店"卖完"是常态，所以报警的是另外两种情况：
      剩不少 —— 临打烊还剩一堆，明天该少做（报损风险）
      账不平 —— 余额算出负数，说明流水有漏记，要去盘点
    """
    day = _today(day)
    conn = connect()
    mu = {r["sku_id"]: float(r["mu"] or 0)
          for r in conn.execute("SELECT sku_id, mu FROM sku")}
    sold = {r["sku_id"]: int(r["q"] or 0) for r in conn.execute(
        "SELECT sku_id, SUM(qty) q FROM sales WHERE day=? GROUP BY sku_id", (day,))}
    waste = {r["sku_id"]: int(r["q"] or 0) for r in conn.execute(
        "SELECT sku_id, SUM(-qty) q FROM stock_move "
        "WHERE day=? AND type='报损' GROUP BY sku_id", (day,))}
    hour = {r["sku_id"]: int(r["start_hour"]) for r in conn.execute(
        "SELECT sku_id, MIN(start_hour) start_hour FROM stockout_mark "
        "WHERE day=? GROUP BY sku_id", (day,))}

    rows = []
    for r in metrics.stock_rows(conn, day):
        left = int(r["qty"] or 0)
        n_in = left + sold.get(r["sku_id"], 0) + waste.get(r["sku_id"], 0)
        mu_v = mu.get(r["sku_id"], 0) or 1
        if left < 0:
            flag = "账不平"
        elif left >= mu_v * 0.5:
            flag = "剩不少"
        elif hour.get(r["sku_id"], 24) <= 13 and left <= 0:
            flag = "早卖光"
        else:
            flag = "正常"
        rows.append({
            "sku_id": r["sku_id"], "name": r["name"], "category": r["category"],
            "in": n_in, "sold": sold.get(r["sku_id"], 0),
            "waste": waste.get(r["sku_id"], 0), "left": left,
            "hour": hour.get(r["sku_id"]), "flag": flag,
        })

    summary = {
        "day": day,
        "in": sum(x["in"] for x in rows),
        "sold": sum(x["sold"] for x in rows),
        "waste": sum(x["waste"] for x in rows),
        "left": sum(x["left"] for x in rows),
        "skus": len(rows),
    }
    tips = []
    if summary["sold"] == 0:
        tips.append("这天没有任何销售记录，先确认是不是停业")
        return {"summary": summary, "rows": rows, "tips": tips}
    if summary["in"] and summary["sold"] < summary["in"] * 0.1:
        tips.append(f"这天只录了 {summary['sold']} 件，不到进货的 "
                    f"{summary['sold'] / summary['in']:.0%}，账还没结完，不算「剩不少」")
    else:
        off = [x for x in rows if x["flag"] == "账不平"]
        if off:
            tips.append(f"{len(off)} 个品类账算成了负数，流水有漏记，去「记录 · 盘点」核一下")
        hi = [x for x in rows if x["flag"] == "剩不少"]
        if hi:
            tips.append(f"{len(hi)} 个品类临收工还剩不少（{hi[0]['name']} 等），明天可以少做一点")
        early = [x for x in rows if x["flag"] == "早卖光"]
        if early:
            tips.append(f"{len(early)} 个品类 13 点前就卖光（{early[0]['name']} 等），明天可以多做一点")
    return {"summary": summary, "rows": rows, "tips": tips}
