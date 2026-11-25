# -*- coding: utf-8 -*-
"""复盘：次日误差归因、一个月代价对比、模型指标。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.api import day_review, scoreboard

ui.page("复盘", "🔁")
user = ui.guard()
ui.need_owner(user, "复盘")

st.title("次日复盘")

rows = day_review()
kind_cn = {"model": "预测偏差", "data": "数据问题", "human": "人工调整", "none": "正常"}
if rows:
    st.dataframe(
        [{"品类": r["name"], "预测": r["predicted"], "实际": r["actual"],
          "误差": f"{(r['actual']-r['predicted'])/max(r['predicted'],1)*100:+.0f}%",
          "误差归属": kind_cn[r["kind"]]}
         for r in rows],
        width="stretch", hide_index=True)
else:
    st.info("暂无复盘数据")

st.divider()

sb = scoreboard(30)
st.subheader(f"近 {sb['days']} 天代价对比")
if sb["days"]:
    c1, c2, c3 = st.columns(3)
    c1.metric("实际代价", f"¥{sb['money_actual']:,.0f}")
    c2.metric("按建议代价", f"¥{sb['money_model']:,.0f}")
    c3.metric("差额", f"¥{sb['money_saved']:,.0f}",
              delta=f"{sb['money_saved']/max(sb['money_actual'],1)*100:.0f}%")
    d1, d2 = st.columns(2)
    d1.metric("报废件数", f"{sb['model']['waste']:.0f}",
              delta=f"{sb['model']['waste']-sb['actual']['waste']:+.0f}")
    d2.metric("缺货天数", f"{sb['model']['stockout_days']}",
              delta=f"{sb['model']['stockout_days']-sb['actual']['stockout_days']:+d} 天")
else:
    st.info("数据不足，满两周后再看")

st.divider()

st.subheader("预测精度")
csv_path = Path(__file__).resolve().parent.parent / "docs" / "eval_wape.csv"
if csv_path.exists():
    import pandas as pd
    frame = pd.read_csv(csv_path)
    body = frame[frame["口径"].str.contains("补齐|销量|干净日")]
    st.dataframe(
        [{"口径": r["口径"], "MAPE": f"{r['MAPE']:.1f}%", "WAPE": f"{r['WAPE']:.1f}%",
          "偏差方向": f"{r['WPE']:+.1f}%", "样本": int(r["样本"])}
         for _, r in body.iterrows()], width="stretch", hide_index=True)
    st.caption("WAPE 按件数加权，反映全天总量误差；偏差方向为正表示备货偏多。")
else:
    st.info("尚未生成评估结果")
