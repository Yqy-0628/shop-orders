# -*- coding: utf-8 -*-
"""今日：数据异常、收工账、待决事项、订货清单。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.api import data_issues, today_tasks, day_close, order_list, order_csv

ui.page("今日", "☀️")
user = ui.guard()

close = day_close()
st.title("今日")
st.caption(f"业务日 {close['summary']['day']}　{ui.ROLE_CN[user['role']]}")

# ---------------------------------------------------------------- 数据异常
issues = data_issues()
if issues:
    st.subheader(f"数据异常　{len(issues)} 项")
    for it in issues:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{it['name']}**　{it['message']}")
            c1.caption(it["fix_hint"])
            if c2.button("处理", key=f"fix_{it['sku_id']}"):
                st.session_state["sku_id"] = it["sku_id"]
                st.switch_page("pages/3_记录.py")

# ---------------------------------------------------------------- 收工账
sm = close["summary"]
st.subheader("收工账")
c1, c2, c3, c4 = st.columns(4)
c1.metric("进货", f"{sm['in']:,}")
c2.metric("售出", f"{sm['sold']:,}")
c3.metric("报损", f"{sm['waste']:,}")
c4.metric("剩余", f"{sm['left']:,}")

for tip in close["tips"]:
    st.warning(tip)

with st.expander("按品类明细"):
    st.dataframe(
        [{"品类": r["name"], "进货": r["in"], "售出": r["sold"], "报损": r["waste"],
          "剩余": r["left"],
          "售罄时间": f"{r['hour']}:00" if r["hour"] else "—",
          "状态": r["flag"]}
         for r in close["rows"]],
        width="stretch", hide_index=True)

# ---------------------------------------------------------------- 待决事项
tasks = today_tasks()
st.subheader(f"待决事项　{len(tasks)} 项")
if tasks:
    for t in tasks:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{t['name']}**　{t['title']}")
            c1.caption(t["detail"])
            if c2.button("提单", key=f"go_{t['sku_id']}", type="primary"):
                st.session_state["sku_id"] = t["sku_id"]
                st.switch_page("pages/2_订货.py")
else:
    st.success("无待决事项，全部品类按常规量执行。")

# ---------------------------------------------------------------- 订货清单
lines = order_list()
st.subheader("次日备货清单")
st.caption("系统只给建议量，不下单；导出后发给供货商或后厨")
t1, t2 = st.tabs([f"需进货 {lines['summary']['purchase_kinds']} 款 · "
                  f"{lines['summary']['purchase_qty']} 件",
                  f"自制 {lines['summary']['make_kinds']} 款 · "
                  f"{lines['summary']['make_qty']} 件"])
with t1:
    st.dataframe(
        [{"品名": x["name"], "规格": x["spec"] or "—", "建议量": x["qty"]}
         for x in lines["purchase"]],
        width="stretch", hide_index=True)
    st.download_button("导出进货单（CSV）", order_csv("purchase"),
                       f"进货单_{lines['day']}.csv", "text/csv")
with t2:
    st.dataframe(
        [{"品名": x["name"], "规格": x["spec"] or "—", "建议量": x["qty"]}
         for x in lines["make"]],
        width="stretch", hide_index=True)
    st.download_button("导出自制排产单（CSV）", order_csv("make"),
                       f"排产单_{lines['day']}.csv", "text/csv")
