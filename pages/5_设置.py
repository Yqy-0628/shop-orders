# -*- coding: utf-8 -*-
"""设置：商品档案、账号。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, connect

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
st.subheader("修改商品档案")
st.caption("进价、售价、残值决定临界比，保质期决定报废口径。换一家店时改这里，不用动数据库。")

names = [f"{r['sku_id']}　{r['name']}" for r in rows]
pick = st.selectbox("选商品", names, key="edit_pick")
cur = rows[names.index(pick)]

with st.form("edit_sku"):
    c1, c2, c3, c4 = st.columns(4)
    cost = c1.number_input("进价", 0.1, 99.0, float(cur["cost"]), 0.01, format="%.2f")
    price = c2.number_input("售价", 0.1, 199.0, float(cur["price"]), 0.01, format="%.2f")
    salv = c3.number_input("残值", 0.0, 99.0, float(cur["salvage"]), 0.01, format="%.2f")
    shelf = c4.number_input("保质期（天）", 1, 7, int(cur["shelf_life_days"]), 1)
    submitted = st.form_submit_button("保存", type="primary")

if submitted:
    try:
        api.update_sku(cur["sku_id"], cost, price, salv, int(shelf))
        ratio = (price - cost) / (price - salv)
        st.success(f"已保存：{cur['name']}　新临界比 {ratio:.2f}，订货建议会按新参数重算。")
    except ValueError as e:
        st.error(f"没有保存：{e}")

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
