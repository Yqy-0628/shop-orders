# -*- coding: utf-8 -*-
"""设置：商品档案、账号。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import connect

ui.page("设置", "⚙️")
user = ui.guard()

st.title("⚙️ 设置")

st.subheader("商品档案")
st.caption("进价、售价、保质期决定「多订一件亏多少」，是整套算法的输入")
rows = [dict(r) for r in connect().execute(
    "SELECT sku_id, name, category, cost, price, salvage, shelf_life_days, mu "
    "FROM sku ORDER BY category, sku_id")]
st.dataframe(
    [{"编号": r["sku_id"], "品名": r["name"], "品类": r["category"],
      "进价": r["cost"], "售价": r["price"], "残值": r["salvage"],
      "保质期(天)": r["shelf_life_days"], "日均": round(float(r["mu"]), 1)}
     for r in rows],
    width="stretch", hide_index=True, height=420,
)

st.divider()
st.subheader("当前登录")
c1, c2 = st.columns(2)
c1.write(f"账号：**{user['username']}**")
c2.write(f"角色：**{ui.ROLE_CN[user['role']]}**")
st.caption("店员账号看不到进价与毛利——不是前端隐藏，是查询层就不返回这两个字段。")

st.divider()
st.subheader("演示工具")
if st.button("重建演示数据（会清空所有记录）"):
    st.warning("这个按钮还没接上，等部署前再开。")
