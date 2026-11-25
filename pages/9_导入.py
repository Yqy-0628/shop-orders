# -*- coding: utf-8 -*-
"""导入：商品档案与销售流水两张表。"""
import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, metrics

ui.page("导入", "📥")
user = ui.guard()

st.title("数据导入")


def catalog_block():
    st.caption("一次把全部商品建好：分类、规格、自制还是进货、进价售价、保质期")
    c1, c2 = st.columns([1, 3])
    with c1:
        st.download_button("下载模板", api.catalog_template(), "商品档案模板.csv",
                           "text/csv", width="stretch")
    with c2:
        st.caption("表头固定为：编号,品名,分类,规格,来源,进价,售价,处理价,保质期,条码")

    up = st.file_uploader("上传商品档案 CSV", type=["csv", "txt"], key="sku_up")
    pasted = st.text_area("或粘贴表格内容", height=100, key="sku_paste",
                          placeholder="编号,品名,分类,规格,来源,进价,售价,处理价,保质期",
                          label_visibility="collapsed")
    raw = up.read() if up is not None else (pasted.encode("utf-8") if pasted.strip() else None)
    if not raw:
        return

    try:
        parsed = api.catalog_read(raw)
    except Exception as e:
        st.error(f"文件读取失败：{e}")
        return

    checked = api.catalog_check(parsed["headers"], parsed["rows"])
    if checked["missing"]:
        names = {"sku_id": "编号", "name": "品名", "category": "分类",
                 "cost": "进价", "price": "售价", "shelf": "保质期"}
        st.error("表头缺少：" + "、".join(names.get(k, k) for k in checked["missing"]))
        return

    s_ok, s_bad = len(checked["ok"]), len(checked["bad"])
    m1, m2 = st.columns(2)
    m1.metric("可写入", f"{s_ok} 款")
    m2.metric("异常", f"{s_bad} 行")

    if checked["bad"]:
        with st.expander(f"异常 {s_bad} 行", expanded=True):
            st.dataframe([{"行号": b["line"], "原因": b["reason"], "原文": b["raw"]}
                          for b in checked["bad"][:50]], width="stretch", hide_index=True)

    if checked["ok"]:
        st.dataframe(
            [{"编号": r["sku_id"], "品名": r["name"], "分类": r["category"],
              "规格": r["spec"] or "—", "来源": r["source"], "进价": r["cost"],
              "售价": r["price"], "处理价": r["salvage"], "保质期": r["shelf"]}
             for r in checked["ok"][:30]], width="stretch", hide_index=True)

    if st.button("写入商品档案", type="primary", disabled=not checked["ok"], key="sku_commit"):
        res = api.catalog_commit(checked["ok"])
        st.success(f"新增 {res['created']} 款，更新 {res['updated']} 款")
        st.caption("新增单品暂无销量，满 14 天后参与预测；现在即可收银与打印标签。")


def sale_block():
    st.caption("按模板整理好表，上传后直接写库；表头不用改")
    c1, c2 = st.columns([1, 3])
    with c1:
        st.download_button("下载模板", api.import_template(), "销售流水模板.csv",
                           "text/csv", width="stretch")
    with c2:
        st.caption("表头固定为：日期, 单品, 数量, 单价, 时段；单价与时段可留空")

    up = st.file_uploader("上传 CSV", type=["csv", "txt"], key="sale_up")
    pasted = st.text_area("或粘贴表格内容", height=100, key="sale_paste",
                          placeholder="日期,单品,数量\n2026-11-10,SH203,26",
                          label_visibility="collapsed")
    raw = up.read() if up is not None else (pasted.encode("utf-8") if pasted.strip() else None)
    if not raw:
        return

    try:
        parsed = api.import_read(raw)
    except Exception as e:
        st.error(f"文件读取失败：{e}")
        return

    headers, rows = parsed["headers"], parsed["rows"]
    guess = parsed["guess"]
    missing = [n for k, n in (("day", "日期"), ("sku", "单品"), ("qty", "数量")) if k not in guess]
    if missing:
        st.error("表头缺少：" + "、".join(missing) + "。请按模板整理，或下载模板重填。")
        return

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

    replace = st.checkbox("覆盖这段日期已有的销售记录")
    rng = None
    if replace and s["days"]:
        rng = st.date_input("覆盖区间",
                            value=(datetime.date.fromisoformat(s["days"][0]),
                                   datetime.date.fromisoformat(s["days"][-1])))

    if st.button("写入数据库", type="primary", disabled=not checked["ok"], key="sale_commit"):
        rr = (rng[0].isoformat(), rng[1].isoformat()) if replace and rng and len(rng) == 2 else None
        st.session_state["imp_done"] = api.import_commit(checked["ok"], rr)

    done = st.session_state.get("imp_done")
    if done:
        st.success(f"已写入 {done['rows']} 行 / {done['units']:,} 件，"
                   f"{len(done['days'])} 天、{done['skus']} 款")

    st.divider()
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


t_sku, t_sale = st.tabs(["商品档案", "销售流水"])
with t_sku:
    catalog_block()
with t_sale:
    sale_block()
