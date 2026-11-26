# -*- coding: utf-8 -*-
"""设置：商品档案、参数、账号与权限。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api

ui.page("设置", "⚙️")
user = ui.guard()
owner = user["role"] == "owner"

st.title("设置")

# ---------------------------------------------------------------- 商品档案
st.subheader("商品档案")
st.caption("来源决定进哪张单：自制进排产单，进货进进货单")

rows = api.sku_rows(user["role"])
view = [{"编号": r["sku_id"], "品名": r["name"], "分类": r["category"],
         "规格": r["spec"] or "", "来源": r["source"],
         "供货商": r.get("supplier") or "", "售价": float(r["price"])}
        for r in rows]
if owner:
    for v, r in zip(view, rows):
        v["进价"] = float(r["cost"])
        v["处理价"] = float(r["salvage"])
        v["保质期(天)"] = int(r["shelf_life_days"])
st.dataframe(view, width="stretch", hide_index=True, height=420)

if not owner:
    st.info("进价与毛利对店员账号不可见。")
    st.stop()

st.divider()
st.subheader("修改商品")
st.caption("改一款商品的价、保质期与来源。处理价＝卖不掉时每件还能收回的钱，丢弃填 0")

kw = st.text_input("查找", placeholder="输入编号或名称，如 烘焙04 / 蛋挞",
                   label_visibility="collapsed")
pairs = [(f"{r['sku_id']}　{r['name']}" + (f"（{r['spec']}）" if r["spec"] else ""), r)
         for r in rows]
if kw.strip():
    k = kw.strip().lower()
    pairs = [(s, r) for s, r in pairs
             if k in r["sku_id"].lower() or k in r["name"].lower()]
if not pairs:
    st.info("没有匹配的商品。")
    st.stop()

pick = st.selectbox("选择商品", [s for s, _ in pairs])
cur = dict(next(r for s, r in pairs if s == pick))

with st.form("edit_sku"):
    c1, c2, c3 = st.columns(3)
    source = c1.selectbox("来源", ["自制", "进货"],
                          index=0 if cur["source"] == "自制" else 1)
    spec = c2.text_input("规格/口味", value=cur["spec"] or "")
    shelf = c3.number_input("保质期（天）", 1, 7, int(cur["shelf_life_days"]))
    c4, c5, c6 = st.columns(3)
    cost = c4.number_input("进价", 0.01, 999.0, float(cur["cost"]), 0.01, format="%.2f")
    price = c5.number_input("售价", 0.01, 999.0, float(cur["price"]), 0.01, format="%.2f")
    salv = c6.number_input("处理价", 0.0, 999.0, float(cur["salvage"]), 0.01, format="%.2f")
    supplier = st.text_input("供货商（进货类填，自制留空）",
                             value=cur.get("supplier") or "",
                             help="进货单会按供货商分组，方便分别发给各家")

    if st.form_submit_button("保存", type="primary"):
        try:
            api.update_sku(cur["sku_id"], cost, price, salv, int(shelf))
            api.set_sku_meta(cur["sku_id"], source, spec, supplier)
            st.success(f"{cur['name']} 已保存，收银价与临界比即时生效")
        except ValueError as e:
            st.error(f"未保存：{e}")

st.divider()
st.subheader("账号")

with st.form("reset_clerk"):
    st.markdown("**重置店员密码**")
    u = st.text_input("账号", value="clerk")
    p = st.text_input("新密码（至少 6 位）", type="password")
    if st.form_submit_button("重置"):
        try:
            api.reset_password(u.strip(), p)
            st.success("已重置")
        except ValueError as e:
            st.error(str(e))

st.caption("店主可用全部页面；店员可用今日、订货（只读）、收银、标签、设置（只读）。"
           "切换身份在侧栏「切换账号」。")
