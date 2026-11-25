# -*- coding: utf-8 -*-
"""商品档案批量导入。

表头固定：编号,品名,分类,规格,来源,进价,售价,处理价,保质期,条码
编号已存在就更新档案，不存在就新增；新增的单品没有销量，按冷启动档处理。
"""
from __future__ import annotations

import csv
import io

from . import connect
from .importer import read_bytes

ALIAS = {
    "sku_id": ("编号", "商品编号", "编码", "商品编码", "sku", "id"),
    "name": ("品名", "名称", "商品名称", "name"),
    "category": ("分类", "品类", "类别", "category"),
    "spec": ("规格", "口味", "备注", "spec"),
    "source": ("来源", "生产方式", "自制进货", "source"),
    "cost": ("进价", "成本", "cost"),
    "price": ("售价", "单价", "价格", "price"),
    "salvage": ("处理价", "残值", "salvage"),
    "shelf": ("保质期", "保质天数", "shelf_life_days"),
    "barcode": ("条码", "短码", "条形码", "barcode"),
}

REQUIRED = ("sku_id", "name", "category", "cost", "price", "shelf")
TEMPLATE_HEAD = "编号,品名,分类,规格,来源,进价,售价,处理价,保质期,条码"


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("　", "").replace("_", "")


def guess(headers):
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


def _num(s):
    return float((s or "").strip().replace("￥", "").replace("¥", "").replace(",", ""))


def _source(s, category):
    v = (s or "").strip()
    if v in ("自制", "自做", "现做", "自制现做"):
        return "自制"
    if v in ("进货", "采购", "外购", "配送"):
        return "进货"
    if not v:
        return "自制" if category in ("烘焙", "饮品") else "进货"
    return None


def check(headers, rows, mapping):
    """逐行校验，返回 (可写入的行, 问题行)。行号按表格习惯从 2 起。"""
    ok, bad = [], []
    seen = set()
    for i, r in enumerate(rows, start=2):
        rec = {}
        raw = ",".join(r)
        try:
            for k, idx in mapping.items():
                if idx is None or idx >= len(r):
                    continue
                rec[k] = (r[idx] or "").strip()
            sku_id = rec.get("sku_id", "")
            name = rec.get("name", "")
            category = rec.get("category", "")
            if not sku_id:
                raise ValueError("编号为空")
            if sku_id in seen:
                raise ValueError("编号在本文件内重复")
            if not name:
                raise ValueError("品名为空")
            if not category:
                raise ValueError("分类为空")
            cost = _num(rec.get("cost"))
            price = _num(rec.get("price"))
            salvage = _num(rec.get("salvage") or 0)
            if cost <= 0 or price <= 0:
                raise ValueError("进价与售价必须大于 0")
            if price <= cost:
                raise ValueError("售价必须高于进价")
            if salvage < 0 or salvage >= cost:
                raise ValueError("处理价必须不低于 0 且低于进价")
            shelf = int(float(rec.get("shelf") or 0))
            if not 1 <= shelf <= 7:
                raise ValueError("保质期只支持 1 至 7 天")
            source = _source(rec.get("source"), category)
            if source is None:
                raise ValueError("来源只能写「自制」或「进货」")
            ok.append({"sku_id": sku_id, "name": name, "category": category,
                       "spec": rec.get("spec") or "", "source": source,
                       "cost": cost, "price": price, "salvage": salvage,
                       "shelf": shelf, "barcode": (rec.get("barcode") or "").upper()})
            seen.add(sku_id)
        except Exception as e:
            bad.append({"line": i, "reason": str(e), "raw": raw})
    return ok, bad


def _next_barcode(conn, category):
    """没给条码就按分类补一个：前缀沿用同类已有码，新分类从 SH5 起。"""
    rows = [dict(x) for x in conn.execute("SELECT category, barcode FROM sku")]
    prefix = None
    for x in rows:
        if x["category"] == category and x["barcode"]:
            prefix = x["barcode"][:3]
            break
    if prefix is None:
        used = {x["barcode"][:3] for x in rows if x["barcode"]}
        d = 5
        while "SH%d" % d in used and d < 10:
            d += 1
        prefix = "SH%d" % d
    n = 0
    for x in rows:
        b = x["barcode"] or ""
        if b.startswith(prefix) and b[3:].isdigit():
            n = max(n, int(b[3:]))
    return f"{prefix}{n + 1:02d}"


def commit(ok_rows):
    """写库：已有编号更新档案（不动历史销量），新编号新增。返回新增/更新计数。"""
    conn = connect()
    existing = {r[0] for r in conn.execute("SELECT sku_id FROM sku")}
    taken = {r[0] for r in conn.execute("SELECT barcode FROM sku WHERE barcode IS NOT NULL")}
    created = updated = 0
    for r in ok_rows:
        if r["sku_id"] in existing:
            conn.execute(
                "UPDATE sku SET name=?, category=?, cost=?, price=?, salvage=?, "
                "shelf_life_days=?, source=?, spec=? WHERE sku_id=?",
                (r["name"], r["category"], r["cost"], r["price"], r["salvage"],
                 r["shelf"], r["source"], r["spec"] or None, r["sku_id"]))
            updated += 1
        else:
            barcode = r["barcode"]
            if not barcode or barcode in taken:
                barcode = _next_barcode(conn, r["category"])
            taken.add(barcode)
            conn.execute(
                "INSERT INTO sku (sku_id, barcode, name, category, cost, price, salvage, "
                "shelf_life_days, mu, sigma, source, spec) "
                "VALUES (?,?,?,?,?,?,?,?,0,0,?,?)",
                (r["sku_id"], barcode, r["name"], r["category"], r["cost"], r["price"],
                 r["salvage"], r["shelf"], r["source"], r["spec"] or None))
            created += 1
    conn.commit()
    return {"ok": True, "created": created, "updated": updated,
            "skus": len(ok_rows)}


def template_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEAD.split(","))
    w.writerow(["烘焙01", "吐司", "烘焙", "原味", "自制", "5.90", "11.80", "2.40", "1", "SH201"])
    w.writerow(["烘焙02", "牛角包", "烘焙", "黄油", "自制", "6.10", "12.20", "2.50", "1", "SH202"])
    w.writerow(["饮品01", "美式", "饮品", "中杯", "自制", "3.00", "9.30", "0", "1", "SH301"])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
