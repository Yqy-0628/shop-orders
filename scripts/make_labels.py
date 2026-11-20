# -*- coding: utf-8 -*-
"""批量生成标签 PDF：每款印若干张，直接送去打印。"""
import argparse
import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import connect, labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=10, help="每款印几张")
    ap.add_argument("--out", default=str(ROOT / "docs" / "labels.pdf"))
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="生产日期 YYYY-MM-DD")
    ap.add_argument("--cats", default="", help="只看这些品类，逗号分隔")
    args = ap.parse_args()

    made = datetime.date.fromisoformat(args.date)
    want = [c.strip() for c in args.cats.split(",") if c.strip()]

    rows = [dict(r) for r in connect().execute(
        "SELECT barcode, name, category, price, shelf_life_days FROM sku "
        "WHERE barcode IS NOT NULL ORDER BY barcode")]
    if want:
        rows = [r for r in rows if r["category"] in want]
    if not rows:
        print("没有可用商品")
        return

    items = []
    for r in rows:
        expire = made + datetime.timedelta(days=int(r["shelf_life_days"]))
        items += [{"name": r["name"], "price": float(r["price"]),
                   "barcode": r["barcode"], "shelf": int(r["shelf_life_days"]),
                   "expire": expire.isoformat()} for _ in range(args.per)]

    pdf = labels.to_pdf_bytes(items)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf)
    pages = (len(items) + 23) // 24
    print("items=%d pages=%d bytes=%d -> %s" % (len(items), pages, len(pdf), out))


if __name__ == "__main__":
    main()
