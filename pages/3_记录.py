# -*- coding: utf-8 -*-
"""记录：卖了多少、卖光了、到货、报损，四块并排；盘点收在折叠区。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import connect
from core.api import (record_arrival, record_count, record_sale,
                      record_soldout, record_waste)

ui.page("记录", "📝")
user = ui.guard()

st.title("📝 今天记四件事")
st.caption("店员两三分钟录完，系统第二天才知道该订多少")

names = [dict(r) for r in connect().execute(
    "SELECT sku_id, name FROM sku ORDER BY sku_id")]
labels = {f"{r['sku_id']} {r['name']}": r["sku_id"] for r in names}
default = st.session_state.get("sku_id", names[0]["sku_id"])
idx = next((i for i, v in enumerate(labels.values()) if v == default), 0)

r1c1, r1c2 = st.columns(2)

with r1c1:
    with st.container(border=True):
        st.subheader("① 卖了多少")
        st.caption("卖出一笔记一笔，一天可以记多次")
        with st.form("sale"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="x_sku")
            qty = st.number_input("卖了几件", min_value=1, max_value=999, value=5)
            hour = st.slider("大概几点", 9, 21, 14)
            if st.form_submit_button("记一笔", width="stretch"):
                r = record_sale(labels[pick], int(qty), int(hour))
                st.success(f"{pick.split()[1]} 记了 {qty} 件，当天累计 {r['total']} 件")

with r1c2:
    with st.container(border=True):
        st.subheader("② 卖光了")
        st.caption("整天才点一次，卖完那一刻记")
        with st.form("soldout"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="s_sku")
            hour = st.slider("几点卖完", 9, 21, 15)
            if st.form_submit_button("标记售罄", width="stretch"):
                record_soldout(labels[pick], int(hour))
                st.success(f"{pick.split()[1]} 记为 {hour}:00 售罄")

r2c1, r2c2 = st.columns(2)

with r2c1:
    with st.container(border=True):
        st.subheader("③ 到货")
        st.caption("送货来了，点一下")
        with st.form("arrival"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="a_sku")
            qty = st.number_input("实收数量", min_value=0, max_value=999, value=30)
            if st.form_submit_button("确认到货", width="stretch"):
                r = record_arrival(labels[pick], int(qty))
                nm = pick.split()[1]
                if r["diff"]:
                    st.warning(
                        f"{nm} 应到 {r['expected']}，实收 {qty}，差 {r['diff']:+d} 件 —— "
                        f"已按实收记账，差异留在流水里备查")
                else:
                    st.success(f"{nm} 到货 {qty} 个")

with r2c2:
    with st.container(border=True):
        st.subheader("④ 报损")
        st.caption("卖不掉、过期、坏了")
        with st.form("waste"):
            pick = st.selectbox("品类", list(labels.keys()), index=idx, key="w_sku")
            qty = st.number_input("报废数量", min_value=1, max_value=99, value=2)
            if st.form_submit_button("登记报损", width="stretch"):
                record_waste(labels[pick], int(qty))
                st.success(f"{pick.split()[1]} 报废 {qty} 个")

with st.expander("盘点：账面对不上时用"):
    st.caption("数一遍货架，把实盘数填进来，系统自动补一条「盘点」流水把账调平。")
    with st.form("count"):
        pick = st.selectbox("品类", list(labels.keys()), index=idx, key="c_sku")
        real = st.number_input("实盘还有几件", min_value=0, max_value=999, value=0)
        if st.form_submit_button("按实盘调平"):
            r = record_count(labels[pick], int(real))
            st.success(f"账面 {r['book']} 件 → 实盘 {r['real']} 件，"
                       f"已补 {r['diff']:+d} 件")

st.divider()
st.info("**为什么「卖光了」这么重要**：卖光那天的销量不是需求，是上限。"
        "没有这个标记，系统会以为那天真的只卖了这么多，越畅销的品类被低估得越狠。")
