# -*- coding: utf-8 -*-
"""订货：预测、三档建议、最优量、下单。店员只读。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api
from core.api import predict, suggest, record_decision
from core.readiness import readiness

ui.page("订货", "📦")
user = ui.guard()
owner = user["role"] == "owner"

st.title("订货建议")

r = readiness()
if r["mode"] == "full":
    st.caption(f"数据就绪　{r['label']}　单品中位 {r['median']} 天")
else:
    st.warning(f"数据就绪　{r['label']}　{r['advice']}")

rows = api.sku_rows(user["role"])
labels = [f"{x['sku_id']}　{x['name']}" + (f"（{x['spec']}）" if x["spec"] else "")
          for x in rows]
default = st.session_state.get("sku_id", rows[0]["sku_id"])
idx = next((i for i, x in enumerate(rows) if x["sku_id"] == default), 0)
pick = st.selectbox("商品", labels, index=idx)
sku = rows[labels.index(pick)]["sku_id"]
st.session_state["sku_id"] = sku

p = predict(sku)
c1, c2, c3 = st.columns(3)
c1.metric("次日预计", f"{p['value']} 件")
c2.metric("90% 区间", f"{p['lo']} – {p['hi']}")
c3.metric("置信度", f"{int(p['level']*100)}%")

with st.expander("预测构成"):
    for e in p["explain"]:
        st.write(f"**{e['label']}**：{e['value']}")
    if p["confidence"] == "low":
        st.warning("历史样本不足，结果仅供参考")

st.divider()

st.subheader("三档建议")
s = suggest(sku)
cols = st.columns(3)
for col, t in zip(cols, s["tiers"]):
    with col:
        with st.container(border=True):
            st.markdown(f"**{t['name']}**")
            st.metric("订货量", f"{t['qty']} 件", label_visibility="collapsed")
            st.write(f"预计报废 {t['waste']} 件 ≈ {ui.money(t.get('waste_cost', 0))}")
            st.write(f"预计缺货 {t['short']} 件 ≈ {ui.money(t.get('short_cost', 0))}")
            st.write(f"缺货概率 {t['stockout']*100:.0f}%")
            st.caption(f"两项合计 ≈ {ui.money(t.get('cost_total', 0))}")
            if owner and st.button("选定", key=f"pick_{t['key']}", width="stretch"):
                record_decision(sku, t["qty"])
                st.success(f"已登记：{t['name']} {t['qty']} 件")

opt = s.get("optimum")
if opt:
    with st.container(border=True):
        st.markdown("**最优订货量**")
        a, b, c = st.columns(3)
        a.metric("最优量", f"{opt['qty']} 件")
        b.metric("临界比", f"{opt['cr']:.2f}")
        c.metric("日均 / 标准差", f"{opt['mu']:.0f} / {opt['sigma']:.1f}")
        st.caption(f"缺货少赚 ¥{opt['cu']:.2f}，多订亏 ¥{opt['co']:.2f}；"
                   f"临界比 {opt['cr']:.2f} 即备到这个量有 {opt['cr']*100:.0f}% 把握不断货")
        if owner and st.button("按最优量登记", key="pick_opt", width="stretch"):
            record_decision(sku, int(opt["qty"]))
            st.success(f"已登记：最优量 {opt['qty']} 件")

if owner:
    with st.expander("手工调整数量"):
        qty = st.number_input("订货量", 1, 999, s["tiers"][1]["qty"])
        reason = st.selectbox("调整原因", ["天气", "活动", "经验", "其他"])
        if st.button("按此数量登记"):
            record_decision(sku, int(qty), reason)
            st.success(f"已登记 {qty} 件（{reason}）")
else:
    st.caption("店员账号只读建议，下单需店主操作。")
