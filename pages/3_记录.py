# -*- coding: utf-8 -*-
"""记录：到货、售罄、报损，三块并排。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import connect
from core.api import record_arrival, record_soldout, record_waste

ui.page("记录", "📝")
user = ui.guard()

st.title("📝 今天记三件事")
st.caption("店员三分钟录完，系统第二天才知道该订多少")

names = [dict(r) for r in connect().execute(
    "SELECT sku_id, name FROM sku ORDER BY sku_id")]
labels = {f"{r['sku_id']} {r['name']}": r["sku_id"] for r in names}
default = st.session_state.get("sku_id", names[0]["sku_id"])
idx = next((i for i, v in enumerate(labels.values()) if v == default), 0)

c1, c2, c3 = st.columns(3)

with c1:
    with st.container(border=True):
        st.subheader("① 到货")
        st.caption("送货来了，点一下")
        with st.form("arrival"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="a_sku")
            qty = st.number_input("实收数量", min_value=0, max_value=999, value=30)
            if st.form_submit_button("确认到货", width="stretch"):
                record_arrival(labels[pick], int(qty))
                st.success(f"{pick.split()[1]} 到货 {qty} 个")

with c2:
    with st.container(border=True):
        st.subheader("② 卖光了")
        st.caption("整天才点一次")
        with st.form("soldout"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="s_sku")
            hour = st.slider("几点卖完", 9, 21, 15)
            if st.form_submit_button("标记售罄", width="stretch"):
                record_soldout(labels[pick], int(hour))
                st.success(f"{pick.split()[1]} 记为 {hour}:00 售罄")

with c3:
    with st.container(border=True):
        st.subheader("③ 报损")
        st.caption("卖不掉、过期、坏了")
        with st.form("waste"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="w_sku")
            qty = st.number_input("报废数量", min_value=1, max_value=99, value=2)
            if st.form_submit_button("登记报损", width="stretch"):
                record_waste(labels[pick], int(qty))
                st.success(f"{pick.split()[1]} 报废 {qty} 个")

st.divider()
st.info("**为什么「卖光了」这么重要**：卖光那天的销量不是需求，是上限。"
        "没有这个标记，系统会以为那天真的只卖了这么多，越畅销的品类被低估得越狠。")
