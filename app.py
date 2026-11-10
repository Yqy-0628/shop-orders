# -*- coding: utf-8 -*-
"""首页：一屏看懂这家店的问题。"""
import streamlit as st

import ui
from core.metrics import kpi, DEMO_TODAY

ui.page("首页", "📦")
user = ui.guard()
conn = ui.conn()
k = kpi(conn)

st.title("📦 该订多少")
st.caption(f"小店订货决策台 · 演示数据截至 {DEMO_TODAY} · 当前身份：{ui.ROLE_CN[user['role']]}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("缺货率", ui.pct(k["stockout_rate"]), help="售罄时长 / 营业时长")
c2.metric("报损率", ui.pct(k["spoilage_rate"]), help="报废件数 / 进货件数")
c3.metric("缺货损失（易损品）", ui.money(k["stockout_loss"]))
c4.metric("缺货 / 报损", f"{k['ratio']:.1f} 倍")

st.divider()

left, right = st.columns([1.2, 1])
with left:
    st.subheader("这家店的问题")
    st.markdown(
        f"""
- 缺货损失 **{ui.money(k['stockout_loss'])}**，报损损失 **{ui.money(k['spoilage_loss'])}**
- 店主一直以为报损最贵，实际缺货贵 **{k['ratio']:.1f} 倍**
- 原因：订货按“上周卖多少订多少”，而卖光的那些天，销量本身是假的
"""
    )
with right:
    st.subheader("三个入口")
    st.page_link("pages/1_收银台.py", label="① 去收银台开一单", icon="🧾")
    st.page_link("pages/3_决策台.py", label="③ 去决策台看看该订多少", icon="🎛️")
    st.page_link("pages/4_诊断.py", label="④ 看看哪个品类总订错", icon="📊")

st.divider()
st.caption("提示：换浏览器标签、用 clerk 登录，可以看到店员视角——进价与毛利全部消失。")
