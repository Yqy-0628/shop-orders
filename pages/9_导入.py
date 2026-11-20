# -*- coding: utf-8 -*-
"""导入：把店家原有系统导出的流水接进来，顺手给一笔对账。

三步走：认字段 → 逐行校验 → 写入。校验阶段不碰库，点「写入」才动数据。
单品那一列写编号（SH203）、条码、或者品名，三种都认。
"""
import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, connect, metrics

ui.page("导入", "📥")
user = ui.guard()

st.title("📥 把老系统的账接进来")
st.caption("店家原来用别的软件记账，导出来的表接进这里，系统才有历史可算")

with st.expander("导入的表该长什么样"):
    st.markdown(
        "**必须有的三列**：日期、单品、数量。可选：单价、时段。\n\n"
        "- 日期：`2026-11-20`、`2026/11/20`、`20261120`、带时分秒的都能认\n"
        "- 单品：编号 `SH203`、条码 `SH203`、品名 `菠萝包` 三种写法都行\n"
        "- 数量：正整数；单价留空就用商品档案里的售价\n\n"
        "编码 UTF-8 或 GBK 都行，逗号、分号、制表符分隔都能认。"
    )

st.divider()

# ---------------------------------------------------------------- 一、取文件
c1, c2 = st.columns([1, 3])
with c1:
    st.download_button("下载导入模板", api.import_template(), "导入模板.csv",
                       "text/csv", width="stretch")
with c2:
    st.caption("模板里三行示例，照着填就行")

up = st.file_uploader("选择一个 CSV 文件", type=["csv", "txt"])
pasted = st.text_area("或者直接粘贴一段", height=110,
                      placeholder="日期,单品,数量,单价,时段\n2026-11-10,SH203,26,11.91,9",
                      label_visibility="collapsed")

b1, b2 = st.columns([1, 1])
with b1:
    if st.button("用模板里的示例数据走一遍", width="stretch"):
        st.session_state["imp_demo"] = api.import_template()
        st.rerun()
with b2:
    if st.button("清掉当前这份", width="stretch"):
        st.session_state.pop("imp_demo", None)
        st.session_state.pop("imp_done", None)
        st.rerun()

raw = None
demo = st.session_state.get("imp_demo")
if up is not None:
    raw = up.read()
elif demo:
    raw = demo
    st.caption("现在用的是模板里的示例数据（3 行）；真要导自己的账，上传文件或粘到上面的框里。")
elif pasted.strip():
    raw = pasted.encode("utf-8")

if not raw:
    st.info("还没拿到数据。上传一个 CSV，或者把表格里的一段直接粘进上面的框。")
    st.stop()

try:
    parsed = api.import_read(raw)
except Exception as e:
    st.error(f"这个文件读不了：{e}")
    st.stop()

headers, rows = parsed["headers"], parsed["rows"]
st.success(f"读到 {len(rows)} 行、{len(headers)} 列")

# ---------------------------------------------------------------- 二、认字段
st.subheader("① 认字段")
st.caption("右边是猜的，猜错了在这儿改")

opts = ["(不用)"] + [f"{h}（第{i + 1}列）" for i, h in enumerate(headers)]


def _idx(label):
    if label == "(不用)":
        return None
    return int(label.rsplit("（第", 1)[1].rstrip("列）")) - 1


guess = parsed["guess"]
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    sel = st.selectbox("日期 · 必填", opts, index=(guess["day"] + 1 if "day" in guess else 0))
    map_day = _idx(sel)
with m2:
    sel = st.selectbox("单品 · 必填", opts, index=(guess["sku"] + 1 if "sku" in guess else 0))
    map_sku = _idx(sel)
with m3:
    sel = st.selectbox("数量 · 必填", opts, index=(guess["qty"] + 1 if "qty" in guess else 0))
    map_qty = _idx(sel)
with m4:
    sel = st.selectbox("单价 · 可选", opts, index=(guess["price"] + 1 if "price" in guess else 0))
    map_price = _idx(sel)
with m5:
    sel = st.selectbox("时段 · 可选", opts, index=(guess["hour"] + 1 if "hour" in guess else 0))
    map_hour = _idx(sel)

mapping = {"day": map_day, "sku": map_sku, "qty": map_qty,
           "price": map_price, "hour": map_hour}

if None in (map_day, map_sku, map_qty):
    st.warning("日期、单品、数量三列都要选上，否则认不出这一行是什么。")
    st.stop()

# ---------------------------------------------------------------- 三、校验
st.subheader("② 逐行校验")
st.caption("这一步只是看，不写库")

checked = api.import_check(headers, rows, mapping)
s = checked["summary"]

k1, k2, k3, k4 = st.columns(4)
k1.metric("能导入", f"{s['ok']} 行")
k2.metric("有问题", f"{s['bad']} 行")
k3.metric("涉及单品", f"{s['skus']} 个")
k4.metric("总件数", f"{s['units']:,}")

if s["days"]:
    st.caption(f"日期范围：{s['days'][0]} 到 {s['days'][-1]}（共 {len(s['days'])} 天）")

if checked["bad"]:
    with st.expander(f"有问题的 {s['bad']} 行，点开看原因", expanded=True):
        st.dataframe(
            [{"行号": b["line"], "原因": b["reason"], "原始内容": b["raw"]}
             for b in checked["bad"][:50]],
            width="stretch", hide_index=True)
        if s["bad"] > 50:
            st.caption(f"只显示前 50 行，另有 {s['bad'] - 50} 行同类问题")

if checked["ok"]:
    with st.expander("可导入的前 8 行长这样"):
        st.dataframe(
            [{"日期": r["day"], "单品": f"{r['sku_id']} {r['name']}",
              "数量": r["qty"], "单价": r["price"] if r["price"] is not None else "用档案价",
              "时段": r["hour"] if r["hour"] is not None else 15}
             for r in checked["ok"][:8]],
            width="stretch", hide_index=True)

# ---------------------------------------------------------------- 四、写入
st.subheader("③ 写入并给一笔对账")

st.caption("同一份文件导第二遍会翻倍。要重导，勾上下面这项，先把这段时间的旧记录清掉。")
replace = st.checkbox("先清空这段时间已有的销售记录")
rng = None
if replace and s["days"]:
    rng = st.date_input(
        "清空哪一段",
        value=(datetime.date.fromisoformat(s["days"][0]),
               datetime.date.fromisoformat(s["days"][-1])))

if not checked["ok"]:
    st.warning("没有可导入的行，先去检查上面的字段和素材。")
    st.stop()

if st.button("写入库", type="primary", width="stretch"):
    rr = None
    if replace and rng and len(rng) == 2:
        rr = (rng[0].isoformat(), rng[1].isoformat())
    res = api.import_commit(checked["ok"], rr)
    st.session_state["imp_done"] = res
    st.session_state["imp_range"] = (s["days"][0], s["days"][-1])

if st.session_state.get("imp_done"):
    done = st.session_state["imp_done"]
    st.success(f"写进去了：{done['rows']} 行 / {done['units']:,} 件，"
               f"覆盖 {len(done['days'])} 天、{done['skus']} 个单品（"
               f"{done['days'][0]} 到 {done['days'][-1]}）")
    st.caption("接着做一件事：让店员把这几天盘一遍，账面才不会飘。去「记录 · 盘点」对一下实盘数。")

st.divider()

# ---------------------------------------------------------------- 五、对账
st.subheader("④ 对账：这笔账对不对得上")
st.caption("按天封闭记账：余额 = 当天进货 − 报损 − 售出。剩货不结转到第二天（短保店每天产量固定）")

today = datetime.date.fromisoformat(metrics.biz_day())
d_from, d_to = st.columns(2)
with d_from:
    day_from = st.date_input("从", value=today - datetime.timedelta(days=6))
with d_to:
    day_to = st.date_input("到", value=today)

rec = api.import_reconcile(day_from.isoformat(), day_to.isoformat())

r1, r2, r3 = st.columns(3)
r1.metric("查看区间", f"{rec['summary']['days']} 天")
r2.metric("覆盖单品", f"{rec['summary']['skus']} 个")
r3.metric("对不上的地方", f"{rec['summary']['issues']} 处")

if rec["summary"].get("unsettled"):
    st.info(f"有 {rec['summary']['unsettled']} 天的账还没结完（卖得很少），这几天先不判「漏记」。")

if rec["issues"]:
    st.dataframe(
        [{"日期": i["day"], "单品": f"{i['sku_id']} {i['name']}",
          "类型": i["kind"], "说明": i["detail"]} for i in rec["issues"][:60]],
        width="stretch", hide_index=True)
    if len(rec["issues"]) > 60:
        st.caption(f"只显示前 60 处，另有 {len(rec['issues']) - 60} 处")
else:
    st.success("这一段账是干净的：卖出去的、报掉的、进来的都对得上")

with st.expander("按单品看明细（只列这一段有流水的）"):
    rows_out = [r for r in rec["rows"]
                if r["进货"] or r["报损"] or r["售出"] or r["余额"]]
    st.dataframe(
        [{"日期": r["day"], "单品": f"{r['sku_id']} {r['name']}",
          "进货": r["进货"], "报损": r["报损"],
          "售出": r["售出"], "余额": r["余额"]} for r in rows_out],
        width="stretch", hide_index=True)
    st.caption("余额是当天算出来的，不等于实盘数。想让账准，就去「记录 · 盘点」定期核一次。")
