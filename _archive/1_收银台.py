# -*- coding: utf-8 -*-
"""收银台：开单、扣库存、一键售罄。"""
import datetime as dt

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.metrics import stock_rows, DEMO_TODAY
from core.auth import can_see_cost

ui.page("收银台", "🧾")
user = ui.guard()
conn = ui.conn()
show_cost = can_see_cost(user["role"])

st.title("🧾 今日柜台")
st.caption(f"{DEMO_TODAY} · {ui.ROLE_CN[user['role']]}视角")

rows = stock_rows(conn, DEMO_TODAY)
table = []
for r in rows:
    line = {"SKU": r["sku_id"], "品名": r["name"], "售价": r["price"], "剩余": r["qty"]}
    if show_cost:
        line["进价"] = r["cost"]
        line["单件毛利"] = round(r["price"] - r["cost"], 2)
    table.append(line)

c1, c2 = st.columns([1.3, 1])
with c1:
    st.subheader("库存")
    st.dataframe(table, width="stretch", hide_index=True, height=380)

with c2:
    st.subheader("开单")
    avail = [r for r in rows if r["qty"] > 0]
    with st.form("sale"):
        pick = st.selectbox("商品", [f"{r['sku_id']} {r['name']}" for r in avail])
        qty = st.number_input("数量", min_value=1, max_value=50, value=1)
        ok = st.form_submit_button("开单", width="stretch")
    if ok:
        sku = pick.split()[0]
        stock = next(r["qty"] for r in avail if r["sku_id"] == sku)
        if qty > stock:
            st.error(f"库存不够，只剩 {stock} 件")
        else:
            today = dt.date.fromisoformat(DEMO_TODAY)
            conn.execute(
                "INSERT INTO sales (sku_id, day, hour, weekday, qty, unit_price) "
                "VALUES (?,?,?,?,?,?)",
                (sku, DEMO_TODAY, dt.datetime.now().hour, today.weekday(), qty,
                 next(r["price"] for r in avail if r["sku_id"] == sku)),
            )
            conn.commit()
            st.success(f"已开单：{sku} × {qty}")
            st.rerun()

    st.divider()
    st.subheader("卖完了")
    st.caption("一整天才点一次，10 秒都不用")
    with st.form("soldout"):
        pick2 = st.selectbox("哪个卖完了", [f"{r['sku_id']} {r['name']}" for r in rows])
        ok2 = st.form_submit_button("标记售罄", width="stretch")
    if ok2:
        sku = pick2.split()[0]
        h = dt.datetime.now().hour
        conn.execute(
            "INSERT INTO stockout_mark (sku_id, day, start_hour, end_hour) VALUES (?,?,?,?)",
            (sku, DEMO_TODAY, h, 21),
        )
        conn.commit()
        st.success(f"{sku} 已标记售罄（{h}:00 起）")
        st.rerun()

st.divider()
st.caption("店员账号看不到进价与毛利——同一套数据，不同角色看到不同信息。")
