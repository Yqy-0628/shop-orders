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
    "supplier": ("供货商", "供应商", "供应商名称", "supplier"),
}

REQUIRED = ("sku_id", "name", "category", "cost", "price", "shelf")
TEMPLATE_HEAD = "编号,品名,分类,规格,来源,进价,售价,处理价,保质期,条码,供货商"


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
                       "shelf": shelf, "barcode": (rec.get("barcode") or "").upper(),
                       "supplier": (rec.get("supplier") or "").strip()})
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


def next_sku_id(conn, category):
    """按分类顺延编号：日配01 之后就是 日配02。"""
    stem = category.strip()
    n = 0
    for (sid,) in conn.execute("SELECT sku_id FROM sku"):
        if sid.startswith(stem) and sid[len(stem):].isdigit():
            n = max(n, int(sid[len(stem):]))
    return f"{stem}{n + 1:02d}"


def add_one(name, category, cost, price, shelf, spec="", source="",
            salvage=0.0, supplier="", barcode=""):
    """手工上架一款新品：编号与条码都自动给，校验规则与批量导入一致。

    返回 {"sku_id", "barcode"}。同名、同码、价格倒挂都会抛 ValueError。
    """
    conn = connect()
    name = (name or "").strip()
    category = (category or "").strip()
    spec = (spec or "").strip()
    if not name:
        raise ValueError("品名不能为空")
    if not category:
        raise ValueError("分类不能为空")
    if conn.execute("SELECT 1 FROM sku WHERE name=?", (name,)).fetchone():
        raise ValueError(f"已有同名商品：{name}，请换个名字或直接改它的档案")

    cost, price = float(cost), float(price)
    salvage = float(salvage or 0)
    shelf = int(shelf)
    if cost <= 0 or price <= 0:
        raise ValueError("进价与售价必须大于 0")
    if price <= cost:
        raise ValueError("售价必须高于进价")
    if salvage < 0 or salvage >= cost:
        raise ValueError("处理价必须不低于 0 且低于进价")
    if not 1 <= shelf <= 7:
        raise ValueError("保质期只支持 1 至 7 天")

    src = _source(source, category)
    if src is None:
        raise ValueError("来源只能选「自制」或「进货」")

    sku_id = next_sku_id(conn, category)
    barcode = (barcode or "").strip().upper()
    if barcode:
        if conn.execute("SELECT 1 FROM sku WHERE barcode=?", (barcode,)).fetchone():
            raise ValueError(f"条码 {barcode} 已被占用")
    else:
        barcode = _next_barcode(conn, category)

    conn.execute(
        "INSERT INTO sku (sku_id, barcode, name, category, cost, price, salvage, "
        "shelf_life_days, mu, sigma, source, spec, supplier) "
        "VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?)",
        (sku_id, barcode, name, category, cost, price, salvage, shelf,
         src, spec or None, (supplier or "").strip() or None))
    conn.commit()
    return {"sku_id": sku_id, "barcode": barcode}


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
            # 供货商留空表示"沿用原值"，免得一次导入把已填的抹掉
            if r.get("supplier"):
                conn.execute("UPDATE sku SET supplier=? WHERE sku_id=?",
                             (r["supplier"], r["sku_id"]))
            updated += 1
        else:
            barcode = r["barcode"]
            if not barcode or barcode in taken:
                barcode = _next_barcode(conn, r["category"])
            taken.add(barcode)
            conn.execute(
                "INSERT INTO sku (sku_id, barcode, name, category, cost, price, salvage, "
                "shelf_life_days, mu, sigma, source, spec, supplier) "
                "VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?)",
                (r["sku_id"], barcode, r["name"], r["category"], r["cost"], r["price"],
                 r["salvage"], r["shelf"], r["source"], r["spec"] or None,
                 r.get("supplier") or None))
            created += 1
    conn.commit()
    return {"ok": True, "created": created, "updated": updated,
            "skus": len(ok_rows)}


def template_csv():
    """模板直接取库里的全部商品，店家改这个文件再导回来就是全量档案。"""
    conn = connect()
    rows = [dict(r) for r in conn.execute(
        "SELECT sku_id, name, category, spec, source, cost, price, salvage, "
        "shelf_life_days, barcode, supplier FROM sku ORDER BY category, sku_id")]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEAD.split(","))
    if rows:
        for r in rows:
            w.writerow([r["sku_id"], r["name"], r["category"], r["spec"] or "",
                        r["source"], f"{r['cost']:.2f}", f"{r['price']:.2f}",
                        f"{r['salvage']:.2f}", r["shelf_life_days"],
                        r["barcode"] or "", r["supplier"] or ""])
    else:
        w.writerow(["日配01", "牛奶", "日配", "950ml", "进货", "3.50", "6.20",
                    "1.20", "3", "SH101", "日配供应商"])
        w.writerow(["烘焙01", "吐司", "烘焙", "原味", "自制", "5.90", "11.80",
                    "2.40", "1", "SH201", ""])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
