# -*- coding: utf-8 -*-
"""进货入库。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.metrics import DEMO_TODAY
from core.auth import can_see_cost

ui.page("进货入库", "📥")
user = ui.guard()
conn = ui.conn()
show_cost = can_see_cost(user["role"])

st.title("📥 进货入库")
st.caption(DEMO_TODAY)

rows = conn.execute("SELECT sku_id, name, cost FROM sku ORDER BY category, sku_id").fetchall()

with st.form("in"):
    pick = st.selectbox("商品", [f"{r['sku_id']} {r['name']}" for r in rows])
    qty = st.number_input("到货数量", min_value=1, max_value=500, value=10)
    cost = st.number_input("进价（元）", min_value=0.1, max_value=99.0, value=3.0, step=0.1)
    ok = st.form_submit_button("入库", width="stretch")

if ok:
    sku = pick.split()[0]
    conn.execute(
        "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
        "VALUES (?,?,'入库',?,?,'已到货')",
        (sku, DEMO_TODAY, qty, cost),
    )
    conn.commit()
    st.success(f"已入库 {sku} × {qty}")
    st.rerun()

st.divider()
st.subheader("今天的实物变动")
data = conn.execute(
    """SELECT m.type, m.sku_id, s.name, m.qty, m.unit_cost, m.status
       FROM stock_move m JOIN sku s ON s.sku_id=m.sku_id
       WHERE m.day=? ORDER BY m.id DESC""",
    (DEMO_TODAY,),
).fetchall()
if data:
    out = []
    for d in data:
        line = {"类型": d["type"], "SKU": d["sku_id"], "品名": d["name"],
                "数量": d["qty"], "状态": d["status"]}
        if show_cost:
            line["单价"] = d["unit_cost"]
        out.append(line)
    st.dataframe(out, width="stretch", hide_index=True)
else:
    st.info("今天还没有实物变动记录")
