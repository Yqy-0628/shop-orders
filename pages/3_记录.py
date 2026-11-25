# -*- coding: utf-8 -*-
"""记录：补录销量、到货、报损、盘点。售罄标记在收银页。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import connect
from core.api import record_arrival, record_count, record_sale, record_waste

ui.page("记录", "📝")
user = ui.guard()

st.title("业务记录")

names = [dict(r) for r in connect().execute(
    "SELECT sku_id, name, spec FROM sku ORDER BY sku_id")]
labels = {f"{r['sku_id']} {r['name']}" + (f" {r['spec']}" if r["spec"] else ""): r["sku_id"]
          for r in names}
default = st.session_state.get("sku_id", names[0]["sku_id"])
idx = next((i for i, v in enumerate(labels.values()) if v == default), 0)

c1, c2 = st.columns(2)

with c1:
    with st.container(border=True):
        st.subheader("补录销量")
        with st.form("sale"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="x_sku")
            qty = st.number_input("件数", 1, 999, 5)
            hour = st.slider("时段", 9, 21, 14)
            if st.form_submit_button("记录", width="stretch"):
                r = record_sale(labels[pick], int(qty), int(hour))
                st.success(f"{pick.split()[1]} 当日累计 {r['total']} 件")

with c2:
    with st.container(border=True):
        st.subheader("到货登记")
        with st.form("arrival"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="a_sku")
            qty = st.number_input("实收数量", 0, 999, 30)
            if st.form_submit_button("确认到货", width="stretch"):
                r = record_arrival(labels[pick], int(qty))
                nm = pick.split()[1]
                if r["diff"]:
                    st.warning(f"{nm} 应到 {r['expected']}，实收 {qty}，差 {r['diff']:+d} 件")
                else:
                    st.success(f"{nm} 到货 {qty} 件")

c3, c4 = st.columns(2)

with c3:
    with st.container(border=True):
        st.subheader("报损登记")
        with st.form("waste"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="w_sku")
            qty = st.number_input("报废件数", 1, 99, 2)
            if st.form_submit_button("登记报损", width="stretch"):
                record_waste(labels[pick], int(qty))
                st.success(f"{pick.split()[1]} 报废 {qty} 件")

with c4:
    with st.container(border=True):
        st.subheader("盘点校正")
        with st.form("count"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="c_sku")
            real = st.number_input("实盘数量", 0, 999, 0)
            if st.form_submit_button("按实盘调平", width="stretch"):
                r = record_count(labels[pick], int(real))
                st.success(f"账面 {r['book']} → 实盘 {r['real']}，调整 {r['diff']:+d}")
