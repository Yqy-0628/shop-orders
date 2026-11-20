# -*- coding: utf-8 -*-
"""CSV 导入与对账。

店家原来用别的系统记账的，把导出的表接进来，系统才有历史可算。
分三步，写库之前不动数据：
  1. 认字段——按常见表头猜出「日期 / 单品 / 数量 / 单价 / 时段」；
  2. 逐行校验——日期能不能认、单品能不能对上（编号、条码、品名都试）、数量是不是正整数；
  3. 写入并给出一笔账——期初加进货减报损，跟售出对得上才叫干净。
"""
from __future__ import annotations

import csv
import datetime
import io

from . import connect

ALIAS = {
    "day": ("日期", "销售日期", "业务日期", "date", "day", "时间"),
    "sku": ("单品", "商品", "商品编码", "商品名称", "品名", "sku", "sku_id", "条码", "barcode", "name"),
    "qty": ("数量", "销量", "售出数量", "件数", "qty", "quantity"),
    "price": ("单价", "售价", "成交单价", "price", "unit_price"),
    "hour": ("小时", "时段", "hour", "时刻"),
}

REQUIRED = ("day", "sku", "qty")


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("　", "").replace("_", "")


def read_bytes(raw: bytes):
    """把上传的字节解成 (表头, 数据行)。逗号、分号、制表符都认。"""
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("文件编码既不是 UTF-8 也不是 GBK，请在 Excel 里另存为「CSV UTF-8」")
    head = text.splitlines()[0] if text else ""
    delim = ","
    if head.count(";") > head.count(","):
        delim = ";"
    elif head.count("\t") > head.count(","):
        delim = "\t"
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        raise ValueError("文件是空的")
    headers = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any((c or "").strip() for c in r)]
    return headers, body


def guess_map(headers):
    """按别名猜字段。猜错不要紧，页面里可以改。"""
    m = {}
    used = set()
    for key, names in ALIAS.items():
        want = {_norm(n) for n in names}
        for i, h in enumerate(headers):
            if i in used:
                continue
            if _norm(h) in want:
                m[key] = i
                used.add(i)
                break
    return m


def norm_day(s):
    """认 2026-11-20、2026/11/20、20261120、2026-11-20 08:30 这几种写法。"""
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    s = s.split(" ")[0].split("T")[0]
    parts = s.split("-")
    if len(parts) == 3:
        y, mo, d = parts
        if len(y) == 2:
            y = "20" + y
        try:
            return datetime.date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return None
    if len(s) == 8 and s.isdigit():
        try:
            return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
        except ValueError:
            return None
    return None


def _skus():
    return [dict(r) for r in connect().execute(
        "SELECT sku_id, barcode, name FROM sku ORDER BY sku_id")]


def resolve_sku(value, skus):
    """编号、条码、品名三种写法都试一遍，只认唯一命中。"""
    v = (value or "").strip()
    if not v:
        return None
    for s in skus:
        if v == s["sku_id"]:
            return s
    up = v.upper()
    for s in skus:
        if s.get("barcode") and up == s["barcode"].upper():
            return s
    for s in skus:
        if v == s["name"]:
            return s
    cands = [s for s in skus if v in s["name"] or s["name"] in v]
    if len(cands) == 1:
        return cands[0]
    return None


def check(headers, rows, mapping, skus=None):
    """逐行校验。返回 (可导入行, 问题行)。不写库。"""
    skus = skus or _skus()
    ok, bad = [], []

    for i, r in enumerate(rows, start=2):
        def get(k):
            idx = mapping.get(k)
            if idx is None or idx >= len(r):
                return ""
            return (r[idx] or "").strip()

        day = norm_day(get("day"))
        if day is None:
            bad.append({"line": i, "raw": " | ".join(r), "reason": "日期认不出来"})
            continue

        s = resolve_sku(get("sku"), skus)
        if s is None:
            bad.append({"line": i, "raw": " | ".join(r),
                        "reason": "单品对不上：%s" % (get("sku") or "(空)")})
            continue

        qty_s = get("qty").replace(",", "")
        try:
            qty = int(float(qty_s))
        except Exception:
            qty = None
        if qty is None or qty <= 0:
            bad.append({"line": i, "raw": " | ".join(r),
                        "reason": "数量不是正整数：%s" % (qty_s or "(空)")})
            continue

        price = None
        if mapping.get("price") is not None:
            ps = get("price").replace("￥", "").replace("¥", "").replace(",", "")
            try:
                price = float(ps) if ps else None
            except Exception:
                price = None
        if price is not None and price <= 0:
            price = None

        hour = None
        if mapping.get("hour") is not None:
            hs = get("hour")
            try:
                hour = int(float(hs.split(":")[0])) if hs else None
            except Exception:
                hour = None
        if hour is not None and not 0 <= hour <= 23:
            hour = None

        ok.append({"line": i, "sku_id": s["sku_id"], "name": s["name"], "day": day,
                   "qty": qty, "price": price, "hour": hour})

    return ok, bad


def commit(rows, replace_range=None):
    """把校验过的行写进 sales。replace_range=(from,to) 时先清空该区间的销售。"""
    conn = connect()
    if replace_range:
        conn.execute("DELETE FROM sales WHERE day>=? AND day<=?", replace_range)
    prices = {r["sku_id"]: r["price"] for r in conn.execute(
        "SELECT sku_id, price FROM sku")}

    n = 0
    days, skus = set(), set()
    for r in rows:
        price = r["price"] if r["price"] is not None else prices.get(r["sku_id"])
        h = r["hour"] if r["hour"] is not None else 15
        wd = datetime.date.fromisoformat(r["day"]).weekday()
        conn.execute(
            "INSERT INTO sales (sku_id, day, hour, weekday, qty, unit_price) "
            "VALUES (?,?,?,?,?,?)",
            (r["sku_id"], r["day"], h, wd, r["qty"], price))
        n += 1
        days.add(r["day"])
        skus.add(r["sku_id"])
    conn.commit()
    return {"rows": n, "days": sorted(days), "skus": len(skus),
            "units": sum(r["qty"] for r in rows)}


def reconcile(day_from, day_to):
    """按单品×天算一笔账，只把对不上的挑出来。

    本系统是「按天封闭」记账：当天的货当天卖、当天报损，剩货不自动结转到第二天
    （短保店每天的产量固定、几乎不留隔夜，结转反而会把账做虚）。
    所以可用量就是当天进货，余额 = 进货 − 报损 − 售出。

    三种矛盾会被挑出来：卖得比进的还多、标了卖光但账上还有货、进了货却一件没卖也没标售罄。
    """
    conn = connect()
    skus = [dict(r) for r in conn.execute("SELECT sku_id, name FROM sku ORDER BY sku_id")]

    inflow, waste, sold, marks = {}, {}, {}, {}
    for r in conn.execute(
            "SELECT sku_id, day, type, SUM(qty) AS q FROM stock_move "
            "WHERE status='已到货' AND day>=? AND day<=? GROUP BY sku_id, day, type",
            (day_from, day_to)):
        key = (r["sku_id"], r["day"])
        if r["type"] == "入库":
            inflow[key] = int(r["q"] or 0)
        elif r["type"] == "报损":
            waste[key] = -int(r["q"] or 0)
    for r in conn.execute(
            "SELECT sku_id, day, SUM(qty) AS q FROM sales "
            "WHERE day>=? AND day<=? GROUP BY sku_id, day", (day_from, day_to)):
        sold[(r["sku_id"], r["day"])] = int(r["q"] or 0)
    for r in conn.execute(
            "SELECT sku_id, day FROM stockout_mark WHERE day>=? AND day<=?",
            (day_from, day_to)):
        marks[(r["sku_id"], r["day"])] = True

    out = []
    issues = []
    d0 = datetime.date.fromisoformat(day_from)
    d1 = datetime.date.fromisoformat(day_to)
    step = datetime.timedelta(days=1)

    # 哪几天整体上还没录完（售出不到进货的两成）—— 这种日子不逐个报「漏记」
    day_in, day_sold = {}, {}
    for (sid, day), q in inflow.items():
        day_in[day] = day_in.get(day, 0) + q
    for (sid, day), q in sold.items():
        day_sold[day] = day_sold.get(day, 0) + q
    unsettled = {d for d, q in day_in.items()
                 if q > 0 and day_sold.get(d, 0) < q * 0.2}

    for s in skus:
        d = d0
        while d <= d1:
            key = (s["sku_id"], d.isoformat())
            got = inflow.get(key, 0)
            lost = waste.get(key, 0)
            sell = sold.get(key, 0)
            end = got - lost - sell
            out.append({"sku_id": s["sku_id"], "name": s["name"], "day": d.isoformat(),
                        "期初": 0, "进货": got, "报损": lost, "售出": sell, "余额": end})

            if sell > got:
                issues.append({"sku_id": s["sku_id"], "name": s["name"], "day": d.isoformat(),
                               "kind": "超卖",
                               "detail": "卖出 %d 件，当天只进了 %d 件，入库漏记了" % (sell, got)})
            if marks.get(key) and end > 0:
                issues.append({"sku_id": s["sku_id"], "name": s["name"], "day": d.isoformat(),
                               "kind": "售罄矛盾",
                               "detail": "标了卖光，按账还剩 %d 件" % end})
            if got > 0 and sell == 0 and not marks.get(key) \
                    and d.isoformat() not in unsettled:
                issues.append({"sku_id": s["sku_id"], "name": s["name"], "day": d.isoformat(),
                               "kind": "疑似漏记",
                               "detail": "进了 %d 件，当天一件没卖也没标售罄" % got})
            d += step

    for day in sorted(unsettled):
        pct = int(day_sold.get(day, 0) * 100 / max(1, day_in.get(day, 1)))
        issues.append({"sku_id": "", "name": "整天", "day": day, "kind": "账未结完",
                       "detail": f"这天只录了 {day_sold.get(day, 0)} 件销量，"
                                 f"不到进货的 {pct}%，先等结完再对"})
    return {"rows": out, "issues": issues,
            "summary": {"days": (d1 - d0).days + 1, "skus": len(skus),
                        "issues": len(issues), "unsettled": len(unsettled)}}


def template_csv() -> bytes:
    """给店家看的空模板，表头固定成猜得出来的写法。"""
    lines = ["日期,单品,数量,单价,时段",
             "2026-11-10,SH203,26,11.91,9",
             "2026-11-10,SH302,13,9.05,10",
             "2026-11-10,SH402,14,15.46,11"]
    return ("\ufeff" + "\n".join(lines) + "\n").encode("utf-8")
