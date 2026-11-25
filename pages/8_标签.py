# -*- coding: utf-8 -*-
"""标签打印：按分类选款、填当日数量、生成 PDF。数量自动沿用上次。"""
import datetime
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, labels

ui.page("标签", "🏷️")
user = ui.guard()

st.title("打印标签")

if not labels.FONT_OK:
    st.warning("当前环境缺少中文字体，标签中的中文会显示为方块。请在本地运行，"
               "或执行 python scripts/make_labels.py 生成 PDF。")


@st.cache_data(show_spinner="正在生成 PDF")
def render(items_json: str):
    items = json.loads(items_json)
    return labels.to_png_bytes(items), labels.to_pdf_bytes(items)


rows = api.sku_rows(user["role"])
if not rows:
    st.info("商品档案为空。")
    st.stop()

cats = sorted({r["category"] for r in rows})
sel = st.multiselect("分类", cats, default=cats)
made = st.date_input("生产日期", value=datetime.date.today())

last = api.label_plan()
base = [r for r in rows if r["category"] in sel]

frame = pd.DataFrame([{
    "商品": r["name"],
    "规格": r["spec"] or "",
    "上次": int(last.get(r["sku_id"], 0)),
    "本次": (int(last.get(r["sku_id"], 0)) or int(round(float(r.get("mu") or 0)))),
    "_id": r["sku_id"],
} for r in base])

if frame.empty:
    st.info("该分类下没有商品。")
    st.stop()

st.caption("本次数量默认沿用上次打印，可直接修改")
edited = st.data_editor(
    frame, hide_index=True, width="stretch",
    column_config={
        "商品": st.column_config.TextColumn(disabled=True, width="medium"),
        "规格": st.column_config.TextColumn(disabled=True, width="small"),
        "上次": st.column_config.NumberColumn(disabled=True, width="small"),
        "本次": st.column_config.NumberColumn(min_value=0, max_value=200, step=1, width="small"),
        "_id": None,
    },
    key="label_editor",
)

total = int(edited["本次"].sum())
pages = max(1, (total + 23) // 24)
st.caption(f"合计 {total} 枚　约 {pages} 页 A4（3 列 × 8 行，每枚 62 × 34 毫米）")

if st.button("生成标签", type="primary", disabled=total == 0):
    plan = {r["_id"]: int(r["本次"]) for _, r in edited.iterrows() if int(r["本次"]) > 0}
    api.save_label_plan(plan)
    items = []
    for _, r in edited.iterrows():
        n = int(r["本次"])
        if n <= 0:
            continue
        src = next(x for x in base if x["sku_id"] == r["_id"])
        expire = made + datetime.timedelta(days=int(src["shelf_life_days"]))
        items += [{"name": src["name"], "price": float(src["price"]),
                   "barcode": src["barcode"], "shelf": int(src["shelf_life_days"]),
                   "expire": expire.isoformat()} for _ in range(n)]
    png, pdf = render(json.dumps(items, ensure_ascii=False))
    if png:
        st.image(png, caption="首页预览", width="stretch")
    if pdf:
        st.download_button("下载 PDF", data=pdf,
                           file_name=f"labels_{made.isoformat()}.pdf", mime="application/pdf")
    else:
        st.error("生成失败，检查字体与条码库。")
