# -*- coding: utf-8 -*-
"""导入链路端到端自检：空库 → 商品档案 → 销售流水 → 今日/订货/复盘能不能跑。

全程在一个临时库里做，不碰 data/shop.db。

    python scripts/verify_import_flow.py
"""
import csv
import io
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core                       # noqa: E402
from core import api              # noqa: E402

DATA = ROOT / "data"
LAST_DAYS = 28


def build_catalog_csv():
    """拿 data/sku.csv 当店家填好的档案：补上规格、来源、供货商三列。"""
    src = list(csv.DictReader(open(DATA / "sku.csv", encoding="utf-8")))
    spec_of = {"日配": "950ml", "烘焙": "原味", "饮品": "中杯", "鲜食": "标准份"}
    supplier_of = {"日配": "日配供应商", "鲜食": "鲜食供应商"}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["编号", "品名", "分类", "规格", "来源", "进价", "售价",
                "处理价", "保质期", "条码", "供货商"])
    for r in src:
        cat = r["category"]
        w.writerow([r["sku_id"], r["name"], cat, spec_of.get(cat, ""),
                    "自制" if cat in ("烘焙", "饮品") else "进货",
                    r["cost"], r["price"], r["salvage"], r["shelf_life_days"],
                    "", supplier_of.get(cat, "")])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def build_sales_csv(days):
    """把 data/sales.csv 的最后 N 天转成店家流水模板的格式。"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日期", "单品", "数量", "单价", "时段"])
    n = 0
    for r in csv.DictReader(open(DATA / "sales.csv", encoding="utf-8")):
        if r["day"] in days:
            w.writerow([r["day"], r["sku_id"], r["qty"], r["unit_price"], r["hour"]])
            n += 1
    return ("\ufeff" + buf.getvalue()).encode("utf-8"), n


def main():
    tmp = Path(tempfile.mkdtemp(prefix="shopverify_"))
    core.DB_PATH = tmp / "verify.db"
    conn = core.connect()
    conn.executescript((DATA / "schema.sql").read_text(encoding="utf-8"))
    conn.close()
    print(f"临时库 {core.DB_PATH}")

    # ① 商品档案
    raw = build_catalog_csv()
    rd = api.catalog_read(raw)
    print(f"① 档案表头 {rd['headers']}　{len(rd['rows'])} 行")
    ck = api.catalog_check(rd["headers"], rd["rows"])
    print(f"   校验 通过 {len(ck['ok'])} / 问题 {len(ck['bad'])} / 缺列 {ck['missing']}")
    for b in ck["bad"][:3]:
        print(f"   ! 第 {b['line']} 行：{b['reason']}")
    res = api.catalog_commit(ck["ok"])
    print(f"   写库 新增 {res['created']} / 更新 {res['updated']}")

    # ② 销售流水
    days = sorted({r["day"] for r in csv.DictReader(open(DATA / "sales.csv", encoding="utf-8"))})
    keep = set(days[-LAST_DAYS:])
    raw2, n = build_sales_csv(keep)
    rd2 = api.import_read(raw2)
    print(f"② 流水表头 {rd2['headers']}　{len(rd2['rows'])} 行（{keep.__len__()} 天）")
    ck2 = api.import_check(rd2["headers"], rd2["rows"], rd2["guess"])
    print(f"   校验 通过 {ck2['summary']['ok']} / 问题 {ck2['summary']['bad']}")
    for b in ck2["bad"][:3]:
        print(f"   ! 第 {b['line']} 行：{b['reason']}")
    ok2 = api.import_commit(ck2["ok"])
    print(f"   写库 {ok2}")

    # ③ 导入后能不能用
    from core.metrics import biz_day
    day = biz_day()
    print(f"③ 业务日 {day}")
    close = api.day_close(day)
    s = close["summary"]
    print(f"   收工账 进 {s['in']} / 卖 {s['sold']} / 损 {s['waste']} / 剩 {s['left']}")
    skus = api.sku_rows("owner")
    print(f"   档案 {len(skus)} 款；来源 自制 "
          f"{sum(1 for x in skus if x['source'] == '自制')} / 进货 "
          f"{sum(1 for x in skus if x['source'] == '进货')}")
    p = api.predict(skus[0]["sku_id"], day)
    print(f"   预测 {skus[0]['name']} 次日 {p['value']} 件，置信度 {p['level']:.0%}")
    sug = api.suggest(skus[0]["sku_id"], day)
    print(f"   三档建议 " + " / ".join(f"{t['name']} {t['qty']}" for t in sug["tiers"]))
    ol = api.order_list(day)
    print(f"   备货清单 进货 {ol['summary']['purchase_qty']} 件 / "
          f"自制 {ol['summary']['make_qty']} 件 / "
          f"供货商 {ol['summary']['suppliers']} 家")

    shutil.rmtree(tmp, ignore_errors=True)
    print("临时库已删除")


if __name__ == "__main__":
    main()
