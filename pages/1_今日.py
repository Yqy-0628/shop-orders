# -*- coding: utf-8 -*-
"""今日：先看数据有没有问题，再看今天要决定什么，其余自动下单。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.api import data_issues, today_tasks, auto_lines

ui.page("今日", "☀️")
user = ui.guard()

st.title("☀️ 今天")
st.caption(f"{ui.ROLE_CN[user['role']]}视角 · 先看数据，再看决定")

# ---------------------------------------------------------------- 数据异常
issues = data_issues()
if issues:
    st.subheader(f"⚠️ 有 {len(issues)} 条数据要你确认")
    st.caption("不处理的话，今天的预测会算错")
    for it in issues:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{it['name']}**　{it['message']}")
            c1.caption(f"→ {it['fix_hint']}")
            if c2.button("去处理", key=f"fix_{it['sku_id']}"):
                st.session_state["sku_id"] = it["sku_id"]
                st.switch_page("pages/3_记录.py")
    st.divider()

# ---------------------------------------------------------------- 待决事项
tasks = today_tasks()
if tasks:
    st.subheader(f"📌 今天要你决定的 {len(tasks)} 件事")
    st.caption("其余的上百件，系统按常规量处理，不打扰你")
    for t in tasks:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{t['name']}**　{t['title']}")
            c1.caption(t["detail"])
            if c2.button("去订货", key=f"go_{t['sku_id']}", type="primary"):
                st.session_state["sku_id"] = t["sku_id"]
                st.switch_page("pages/2_订货.py")
else:
    st.success("今天没有需要你拍板的事，其余品类已按常规量自动下单。")

# ---------------------------------------------------------------- 自动下单
lines = auto_lines()
with st.expander(f"已自动下单 {len(lines)} 个品类（不用你确认）"):
    st.dataframe(
        [{"品类": x["name"], "建议量": x["qty"]} for x in lines],
        width="stretch", hide_index=True,
    )
