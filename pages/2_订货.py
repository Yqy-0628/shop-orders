# -*- coding: utf-8 -*-
"""订货：预测 + 为什么 + 三档 + 下单。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import connect
from core.api import predict, suggest, record_decision

ui.page("订货", "📦")
user = ui.guard()

st.title("📦 明天订多少")

names = [dict(r) for r in connect().execute(
    "SELECT sku_id, name FROM sku ORDER BY sku_id")]
labels = {f"{r['sku_id']} {r['name']}": r["sku_id"] for r in names}
default = st.session_state.get("sku_id", names[0]["sku_id"])
idx = next((i for i, v in enumerate(labels.values()) if v == default), 0)
pick = st.selectbox("选一个品类", list(labels.keys()), index=idx)
sku = labels[pick]
st.session_state["sku_id"] = sku

# ---------------------------------------------------------------- 预测
p = predict(sku)
c1, c2, c3 = st.columns([1.2, 1, 1])
c1.metric("明天预计", f"{p['value']} 件")
c2.metric("90% 区间", f"{p['lo']} – {p['hi']}")
c3.metric("把握程度", f"{int(p['level']*100)}%")

with st.expander("为什么是这个数", expanded=False):
    for e in p["explain"]:
        st.write(f"**{e['label']}**：{e['value']}")
    if p["confidence"] == "low":
        st.warning("这个品类历史数据太少，结果仅供参考")

st.divider()

# ---------------------------------------------------------------- 三档
st.subheader("选一档")
s = suggest(sku)
cols = st.columns(3)
for c, t in zip(cols, s["tiers"]):
    with c:
        with st.container(border=True):
            st.markdown(f"### {t['name']}")
            st.metric("订多少", f"{t['qty']} 个", label_visibility="collapsed")
            st.write(f"预计报废 **{t['waste']}** 个")
            st.write(f"断货概率 **{t['stockout']*100:.0f}%**")
            if st.button("选这档", key=f"pick_{t['key']}", width="stretch"):
                record_decision(sku, t["qty"])
                st.success(f"已下单：{t['name']} {t['qty']} 个")

st.divider()
st.caption("预测是「最可能卖多少」，建议是「为了不断货要备多少」——所以建议量通常比预测高。")

with st.expander("我要自己改数量"):
    qty = st.number_input("实际订多少", min_value=1, max_value=999,
                          value=s["tiers"][1]["qty"])
    reason = st.selectbox("为什么改", ["天气", "活动", "经验", "其他"])
    if st.button("按这个数下单"):
        record_decision(sku, int(qty), reason)
        st.success(f"已下单 {qty} 个，原因：{reason}")
