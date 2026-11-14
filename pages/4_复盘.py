# -*- coding: utf-8 -*-
"""复盘：昨天错在哪，以及这一个月你和系统谁更准。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.api import day_review, scoreboard

ui.page("复盘", "🔁")
user = ui.guard()

st.title("🔁 昨天错在哪")

rows = day_review()
if rows:
    st.subheader("逐条复盘")
    st.dataframe(
        [{"品类": r["name"],
          "预测": r["predicted"],
          "实际": r["actual"],
          "误差": f"{(r['actual']-r['predicted'])/max(r['predicted'],1)*100:+.0f}%",
          "算谁的": {"model": "模型", "data": "数据", "human": "人为", "none": "没问题"}[r["kind"]]}
         for r in rows],
        width="stretch", hide_index=True,
    )
    st.caption("「算谁的」很重要：如果是数据错了（比如忘了点售罄），就不该去调模型。")

st.divider()

# ---------------------------------------------------------------- 记分板
sb = scoreboard()
st.subheader("这一个月，你和系统谁更准")

c1, c2, c3 = st.columns(3)
c1.metric("听系统的", f"{sb['follow']['days']} 天",
          delta=f"平均报废 {sb['follow']['waste']} 个", delta_color="off")
c2.metric("没听系统的", f"{sb['ignore']['days']} 天",
          delta=f"平均报废 {sb['ignore']['waste']} 个", delta_color="off")
c3.metric("多扔了", f"{sb['delta']} 个/天")

st.progress(min(sb["follow"]["days"] / max(sb["follow"]["days"] + sb["ignore"]["days"], 1), 1.0),
            text=f"采纳率 {sb['follow']['days']}/{sb['follow']['days']+sb['ignore']['days']}")

st.caption("这一栏不谈模型准不准，只谈「你的直觉值多少钱」。")
