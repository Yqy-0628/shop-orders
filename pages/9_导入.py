# -*- coding: utf-8 -*-
"""导入：把店家原有系统导出的流水接进来，写库后给一笔对账。"""
import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, metrics

ui.page("导入", "📥")
user = ui.guard()

st.title("导入销售流水")
st.caption("按模板整理好表，上传后直接写库；表头不用改")

c1, c2 = st.columns([1, 3])
with c1:
    st.download_button("下载模板", api.import_template(), "销售流水模板.csv",
                       "text/csv", width="stretch")
with c2:
    st.caption("表头固定为：日期, 单品, 数量, 单价, 时段；单价与时段可留空")

up = st.file_uploader("上传 CSV", type=["csv", "txt"])
pasted = st.text_area("或粘贴表格内容", height=100,
                      placeholder="日期,单品,数量\n2026-11-10,SH203,26",
                      label_visibility="collapsed")

raw = up.read() if up is not None else (pasted.encode("utf-8") if pasted.strip() else None)
if not raw:
    st.stop()

try:
    parsed = api.import_read(raw)
except Exception as e:
    st.error(f"文件读取失败：{e}")
    st.stop()

headers, rows = parsed["headers"], parsed["rows"]
guess = parsed["guess"]
missing = [n for k, n in (("day", "日期"), ("sku", "单品"), ("qty", "数量")) if k not in guess]
if missing:
    st.error("表头缺少：" + "、".join(missing) + "。请按模板整理，或下载模板重填。")
    st.stop()

mapping = {k: guess.get(k) for k in ("day", "sku", "qty", "price", "hour")}
st.success(f"读取 {len(rows)} 行")

checked = api.import_check(headers, rows, mapping)
s = checked["summary"]
k1, k2, k3, k4 = st.columns(4)
k1.metric("可导入", f"{s['ok']} 行")
k2.metric("异常", f"{s['bad']} 行")
k3.metric("单品", f"{s['skus']} 款")
k4.metric("件数", f"{s['units']:,}")
if s["days"]:
    st.caption(f"日期范围 {s['days'][0]} 至 {s['days'][-1]}")

if checked["bad"]:
    with st.expander(f"异常 {s['bad']} 行", expanded=True):
        st.dataframe([{"行号": b["line"], "原因": b["reason"], "原文": b["raw"]}
                      for b in checked["bad"][:50]], width="stretch", hide_index=True)

with st.expander("预览前 8 行"):
    st.dataframe(
        [{"日期": r["day"], "单品": f"{r['sku_id']} {r['name']}", "数量": r["qty"],
          "单价": r["price"] if r["price"] is not None else "档案价",
          "时段": r["hour"] if r["hour"] is not None else 15}
         for r in checked["ok"][:8]], width="stretch", hide_index=True)

st.subheader("写入")
replace = st.checkbox("覆盖这段日期已有的销售记录")
rng = None
if replace and s["days"]:
    rng = st.date_input("覆盖区间",
                        value=(datetime.date.fromisoformat(s["days"][0]),
                               datetime.date.fromisoformat(s["days"][-1])))

if st.button("写入数据库", type="primary", disabled=not checked["ok"]):
    rr = (rng[0].isoformat(), rng[1].isoformat()) if replace and rng and len(rng) == 2 else None
    st.session_state["imp_done"] = api.import_commit(checked["ok"], rr)

done = st.session_state.get("imp_done")
if done:
    st.success(f"已写入 {done['rows']} 行 / {done['units']:,} 件，"
               f"{len(done['days'])} 天、{done['skus']} 款")

st.divider()

# ---------------------------------------------------------------- 对账
st.subheader("对账")
today = datetime.date.fromisoformat(metrics.biz_day())
d1, d2 = st.columns(2)
with d1:
    day_from = st.date_input("起始", value=today - datetime.timedelta(days=6))
with d2:
    day_to = st.date_input("截止", value=today)

rec = api.import_reconcile(day_from.isoformat(), day_to.isoformat())
r1, r2, r3 = st.columns(3)
r1.metric("天数", f"{rec['summary']['days']}")
r2.metric("覆盖单品", f"{rec['summary']['skus']}")
r3.metric("不一致", f"{rec['summary']['issues']} 处")

if rec["summary"].get("unsettled"):
    st.info(f"{rec['summary']['unsettled']} 天账目未结清，暂不判定漏记。")

if rec["issues"]:
    st.dataframe([{"日期": i["day"], "单品": f"{i['sku_id']} {i['name']}",
                   "类型": i["kind"], "说明": i["detail"]} for i in rec["issues"][:60]],
                 width="stretch", hide_index=True)
else:
    st.success("该区间账目一致")

with st.expander("按单品明细"):
    rows_out = [r for r in rec["rows"] if r["进货"] or r["报损"] or r["售出"] or r["余额"]]
    st.dataframe([{"日期": r["day"], "单品": f"{r['sku_id']} {r['name']}",
                   "进货": r["进货"], "报损": r["报损"], "售出": r["售出"], "余额": r["余额"]}
                  for r in rows_out], width="stretch", hide_index=True)
