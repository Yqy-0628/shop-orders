# -*- coding: utf-8 -*-
"""经营看板：这段时间生意怎么样、钱漏在哪、明天先改什么。"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import board, connect

ui.page("看板", "📊")
user = ui.guard()
ui.need_owner(user, "经营看板")

st.title("经营看板")
days = st.radio("看多久", [14, 28, 56], index=1, horizontal=True,
                format_func=lambda d: f"近 {d} 天")

trend = board.daily_trend(days)
if not trend:
    st.info("还没有可统计的数据。")
    st.stop()

df = pd.DataFrame(trend)
cats = board.category_loss(days)
waste_qty = sum(c["waste_qty"] for c in cats)
in_qty = sum(c["in_qty"] for c in cats)
waste_rate = waste_qty / in_qty if in_qty else 0.0
n_sku = connect().execute("SELECT COUNT(*) FROM sku").fetchone()[0] or 1
soldout_share = df["stockouts"].sum() / (n_sku * len(df))

revenue = df["revenue"].sum()
gross = df["gross"].sum()
margin = gross / revenue if revenue else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("销售额", f"¥{revenue:,.0f}")
c2.metric("毛利率", f"{margin * 100:.1f}%")
c3.metric("报损率", f"{waste_rate * 100:.1f}%")
c4.metric("售罄占比", f"{soldout_share * 100:.0f}%")

st.divider()

st.subheader("销量与进货")
line = df.set_index("day")[["sold", "ordered"]].rename(
    columns={"sold": "售出", "ordered": "进货"})
st.line_chart(line, height=260)

if df["stockouts"].max() > 0:
    st.bar_chart(df.set_index("day")["stockouts"].rename("当日售罄单品数"),
                 height=150)

st.divider()

st.subheader("分类损耗")
cat_df = pd.DataFrame(cats).set_index("category")
st.bar_chart(cat_df[["waste_cost"]].rename(columns={"waste_cost": "报损金额（元）"}),
             height=240)
st.dataframe(
    [{"品类": c["category"],
      "报损金额": f"¥{c['waste_cost']:,.0f}",
      "报损率": f"{c['waste_rate'] * 100:.1f}%",
      "卖光天数": c["soldout_days"],
      "进货件数": c["in_qty"]}
     for c in cats],
    width="stretch", hide_index=True,
)

st.divider()

st.subheader("待改进项")
tips = board.headline(days)
if not tips:
    st.success("各项指标均在阈值内")
for t in tips:
    st.markdown(f"- **{t['kind']}｜{t['sku']}**：{t['text']}")

st.caption(
    "口径：销售额 = Σ销量×单价；毛利 = Σ销量×(单价−成本)；"
    "报损率 = 报损件数 / 进货件数；售罄占比 = 有售罄标记的(单品×天) / (单品数×天数)。")

