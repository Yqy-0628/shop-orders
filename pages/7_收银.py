# -*- coding: utf-8 -*-
"""扫码收银：把包装上标签的短码扫进来，一次性记成一单。"""
import datetime
import sys
from collections import Counter
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, connect
from core.metrics import biz_day

ui.page("收银", "🧾")
ui.guard()

st.title("🧾 扫码结账")

day = biz_day()
skus = {r["barcode"]: dict(r) for r in connect().execute(
    "SELECT sku_id, barcode, name, category, price FROM sku "
    "WHERE barcode IS NOT NULL")}

st.caption(f"业务日 {day}　｜　扫码枪就是键盘：连扫会一行一个码，扫完点提交")

today = connect().execute(
    "SELECT COALESCE(SUM(qty),0) AS q, COALESCE(SUM(qty*unit_price),0) AS m "
    "FROM sales WHERE day=?", (day,)).fetchone()

c1, c2, c3 = st.columns(3)
c1.metric("今天已记件数", f"{int(today['q'])} 件")
c2.metric("今天已记金额", f"￥{float(today['m']):.2f}")
c3.metric("可识别的码", f"{len(skus)} 个")

raw = st.text_area("把码扫到这里", height=150, key="scan_box",
                   placeholder="SH203\nSH203\nSH302")

if st.button("提交这一单", type="primary"):
    codes = [ln.strip().upper() for ln in raw.splitlines() if ln.strip()]
    if not codes:
        st.warning("还没有扫到任何码。")
    else:
        unknown = sorted({c for c in codes if c not in skus})
        cnt = Counter(c for c in codes if c in skus)
        hour = max(9, min(21, datetime.datetime.now().hour))
        for barcode, n in cnt.items():
            api.record_sale(skus[barcode]["sku_id"], n, hour)

        lines = []
        total = 0.0
        by_cat = {}
        for barcode, n in cnt.items():
            row = skus[barcode]
            amount = n * float(row["price"])
            total += amount
            by_cat[row["category"]] = by_cat.get(row["category"], 0.0) + amount
            lines.append({"品名": row["name"], "品类": row["category"],
                          "数量": n, "单价": f"￥{float(row['price']):.2f}",
                          "小计": f"￥{amount:.2f}"})

        st.success(f"这一单 {sum(cnt.values())} 件，合计 ￥{total:.2f}")
        st.dataframe(lines, width="stretch", hide_index=True)

        st.caption("按品类：" + "　".join(
            f"{k} ￥{v:.2f}" for k, v in sorted(by_cat.items())))

        if unknown:
            st.error("以下码不在商品档案里，已跳过：" + "、".join(unknown))

st.divider()
st.caption("标签在这里打印：侧栏「标签」页。二维码和条码都能扫，"
           "但一维条码更快、打印成本更低。")
