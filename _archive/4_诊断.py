# -*- coding: utf-8 -*-
"""诊断：哪个品类常年订错。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.metrics import category_deviation, kpi

ui.page("诊断", "📊")
ui.guard()
conn = ui.conn()

st.title("📊 你总是订错哪一类")
st.caption("不是给一个数字，是给一个病因")

rows = category_deviation(conn)
data = [{"品类": r["category"], "平均实际订货": round(r["actual"], 1),
         "建议订货": round(r["suggest"], 1), "偏差": f"{r['gap']*100:+.0f}%"} for r in rows]
st.dataframe(data, width="stretch", hide_index=True)

chart = [{"品类": r["category"], "偏差(%)": round(r["gap"] * 100, 1)} for r in rows]
st.bar_chart(chart, x="品类", y="偏差(%)", height=320)
st.caption("0 以上＝常年多订，0 以下＝常年少订")

worst = min(rows, key=lambda r: r["gap"])
best = max(rows, key=lambda r: r["gap"])
st.markdown(
    f"""
**一句话结论**：**{worst['category']}**常年少订 {abs(worst['gap'])*100:.0f}%，
**{best['category']}**常年多订 {best['gap']*100:.0f}%。
同一套订货习惯，套在不同品类上，一边缺货一边报损。
"""
)

st.divider()
k = kpi(conn)
a, b, c = st.columns(3)
a.metric("缺货率", ui.pct(k["stockout_rate"]))
b.metric("报损率", ui.pct(k["spoilage_rate"]))
c.metric("缺货 / 报损", f"{k['ratio']:.1f} 倍")
