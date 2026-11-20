# -*- coding: utf-8 -*-
"""复盘：昨天错在哪，以及过去一个月「听系统的」能省多少。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.api import day_review, scoreboard

ui.page("复盘", "🔁")
ui.guard()

st.title("🔁 昨天错在哪")

rows = day_review()
if rows:
    st.subheader("逐条复盘")
    kind_cn = {"model": "模型", "data": "数据", "human": "人为", "none": "没问题"}
    st.dataframe(
        [{"品类": r["name"],
          "预测": r["predicted"],
          "实际": r["actual"],
          "误差": f"{(r['actual']-r['predicted'])/max(r['predicted'],1)*100:+.0f}%",
          "算谁的": kind_cn[r["kind"]]}
         for r in rows],
        width="stretch", hide_index=True,
    )
    st.caption("「算谁的」很重要：如果是数据错了（比如那天卖光了），就不该去调模型。")
else:
    st.info("还没有可复盘的数据。")

st.divider()

# ---------------------------------------------------------------- 记分板
sb = scoreboard(30)
st.subheader(f"过去 {sb['days']} 天：如果按建议订，会差多少")

if sb["days"]:
    c1, c2, c3 = st.columns(3)
    c1.metric("实际总代价", f"¥{sb['money_actual']:,.0f}")
    c2.metric("按建议总代价", f"¥{sb['money_model']:,.0f}")
    c3.metric("省下", f"¥{sb['money_saved']:,.0f}",
              delta=f"{sb['money_saved']/max(sb['money_actual'],1)*100:.0f}%",
              delta_color="normal")

    st.markdown("---")
    st.markdown("**但这不是全面胜利**——看看代价是怎么换的：")
    d1, d2 = st.columns(2)
    d1.metric("报废件数", f"{sb['model']['waste']:.0f}",
              delta=f"{sb['model']['waste']-sb['actual']['waste']:+.0f} 件",
              delta_color="inverse")
    d2.metric("断货天数", f"{sb['model']['stockout_days']}",
              delta=f"{sb['model']['stockout_days']-sb['actual']['stockout_days']:+d} 天",
              delta_color="inverse")
    st.caption(
        f"按建议订会**多报 {sb['model']['waste']-sb['actual']['waste']:.0f} 件**，"
        f"但**少断货 {sb['actual']['stockout_days']-sb['model']['stockout_days']} 天**。"
        "报废一件亏成本，断货一件亏毛利——所以总账是省的。"
    )
else:
    st.info("数据不足，攒够两周再看。")

st.divider()

# ---------------------------------------------------------------- 模型体检
st.subheader("模型准不准：MAPE 之外还得看 WAPE")
st.caption("MAPE 把每个单品当成一样重；WAPE 按件数加权，回答的是「一天总共差多少件」")

csv_path = Path(__file__).resolve().parent.parent / "docs" / "eval_wape.csv"
if csv_path.exists():
    import pandas as pd
    frame = pd.read_csv(csv_path)
    body = frame[frame["口径"].str.contains("补齐|销量|干净日")]
    st.dataframe(
        [{"口径": r["口径"],
          "MAPE": f"{r['MAPE']:.1f}%",
          "WAPE": f"{r['WAPE']:.1f}%",
          "WPE（正=备货偏多）": f"{r['WPE']:+.1f}%",
          "样本": int(r["样本"])} for _, r in body.iterrows()],
        width="stretch", hide_index=True)
    st.caption(
        "①「直接用销量」MAPE 更低，但 WPE 是 −10%——每天总体少备一成货，"
        "这正是下午就卖光的原因；② 补齐之后 MAPE 略升、WPE 收窄到 +3%，"
        "说明补齐修的是偏差，不是逐条误差；③ 换指标不是为了让数字更好看，"
        "而是因为它对应老板真正的感受。")
else:
    st.info("还没有评估结果。跑 `python scripts/eval_wape.py` 生成 docs/eval_wape.csv。")
