# -*- coding: utf-8 -*-
"""标签打印：品名、售价、到期日、条码，一张 A4 出 24 枚。"""
import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import connect, labels

ui.page("标签", "🏷️")
ui.guard()

st.title("🏷️ 打印标签")

if not labels.FONT_OK:
    st.warning("中文标签需要本机字体（Windows 黑体）。当前环境没有，"
               "请在本地运行，或执行 python scripts/make_labels.py 生成 PDF。")

rows = [dict(r) for r in connect().execute(
    "SELECT sku_id, barcode, name, category, price, shelf_life_days FROM sku "
    "WHERE barcode IS NOT NULL ORDER BY barcode")]

if not rows:
    st.info("商品档案里还没有条码，先执行 scripts/migrate_barcode.py。")
    st.stop()

cats = sorted({r["category"] for r in rows})
sel = st.multiselect("品类", cats, default=cats)
per = st.slider("每款印几张", 1, 60, 10)
made = st.date_input("生产日期", value=datetime.date.today())

targets = [r for r in rows if r["category"] in sel]
st.caption(f"共 {len(targets)} 款 × {per} 张 = {len(targets) * per} 枚，"
           f"约 {max(1, (len(targets) * per + 23) // 24)} 页 A4（3 列 × 8 行）")

if st.button("生成标签", type="primary"):
    if not targets:
        st.warning("至少选一个品类。")
    else:
        items = []
        for r in targets:
            expire = made + datetime.timedelta(days=int(r["shelf_life_days"]))
            items += [{"name": r["name"], "price": float(r["price"]),
                       "barcode": r["barcode"],
                       "shelf": int(r["shelf_life_days"]),
                       "expire": expire.isoformat()} for _ in range(per)]

        png = labels.to_png_bytes(items)
        if png:
            st.image(png, caption="第一页预览（打印时按实际尺寸）", width="stretch")

        pdf = labels.to_pdf_bytes(items)
        if pdf:
            st.download_button("下载 PDF（直接打印）", data=pdf,
                               file_name="labels_%s.pdf" % made.isoformat(),
                               mime="application/pdf")
        else:
            st.error("生成失败，检查字体与条码库是否可用。")

st.divider()
st.caption("标签纸按 3 列 × 8 行、每枚 62×34 毫米排版。"
           "如果店里的不干胶规格不同，改 core/labels.py 里的 cell_w_mm 与 cell_h_mm。")
