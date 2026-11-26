# -*- coding: utf-8 -*-
"""标签打印：按分类选款、填当日数量、生成 PDF。数量默认沿用上次打印。"""
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
def render(items_json: str, paper_name: str):
    items = json.loads(items_json)
    return (labels.to_png_bytes(items, paper_name),
            labels.to_pdf_bytes(items, paper_name))


rows = api.sku_rows(user["role"])
if not rows:
    st.info("商品档案为空。")
    st.stop()

cats = sorted({r["category"] for r in rows})
c0, c1, c2 = st.columns([2, 2, 2])
sel = c0.multiselect("分类", cats, default=cats)
made = c1.date_input("生产日期", value=datetime.date.today())
paper_name = c2.selectbox("纸张", list(labels.PAPERS.keys()),
                          index=list(labels.PAPERS).index(labels.DEFAULT_PAPER))
cfg = labels.paper(paper_name)
per = cfg["cols"] * cfg["rows"]
st.caption(f"每枚 {cfg['cell_w']}×{cfg['cell_h']} 毫米，一页 {cfg['cols']}×{cfg['rows']}"
           f"＝{per} 枚。换纸只改这里，版式比例自动跟着缩放。")

last = api.label_plan()
base = [r for r in rows if r["category"] in sel]
if not base:
    st.info("该分类下没有商品。")
    st.stop()

ver = int(st.session_state.get("label_ver", 0))
mode = st.session_state.get("label_mode", "last")
b1, b2, b3 = st.columns([1, 1, 3])
if b1.button("数量沿用上次", width="stretch"):
    st.session_state["label_mode"] = "last"
    st.session_state["label_ver"] = ver + 1
if b2.button("全部清零", width="stretch"):
    st.session_state["label_mode"] = "zero"
    st.session_state["label_ver"] = ver + 1

def seed(r):
    prev = int(last.get(r["sku_id"], 0))
    if mode == "zero":
        return 0
    return prev or int(round(float(r.get("mu") or 0)))


frame = pd.DataFrame([{
    "商品": r["name"],
    "分类": r["category"],
    "规格": r["spec"] or "",
    "上次": int(last.get(r["sku_id"], 0)),
    "本次": seed(r),
    "_id": r["sku_id"],
} for r in base])

st.caption("「本次」默认等于上次打印量，只改今天要变动的那几款；改成 0 就不打这款")
edited = st.data_editor(
    frame, hide_index=True, width="stretch",
    column_config={
        "商品": st.column_config.TextColumn(disabled=True, width="medium"),
        "分类": st.column_config.TextColumn(disabled=True, width="small"),
        "规格": st.column_config.TextColumn(disabled=True, width="small"),
        "上次": st.column_config.NumberColumn(disabled=True, width="small"),
        "本次": st.column_config.NumberColumn(min_value=0, max_value=200, step=1, width="small"),
        "_id": None,
    },
    key=f"label_editor_{ver}",
)

qty = edited["本次"].astype(int)
total = int(qty.sum())
kinds = int((qty > 0).sum())
skip = len(edited) - kinds
pages = max(1, (total + per - 1) // per)
st.caption(f"{kinds} 款 · {total} 枚　约 {pages} 页（每页 {per} 枚）"
           + (f"　另有 {skip} 款不打" if skip else ""))

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
    png, pdf = render(json.dumps(items, ensure_ascii=False), paper_name)
    if png:
        st.image(png, caption="首页预览", width="stretch")
    if pdf:
        st.download_button("下载 PDF", data=pdf,
                           file_name=f"labels_{made.isoformat()}.pdf", mime="application/pdf")
    else:
        st.error("生成失败，检查字体与条码库。")
