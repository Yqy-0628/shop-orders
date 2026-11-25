# -*- coding: utf-8 -*-
"""收银：扫码入单、核对小票、结账；售罄也在这里标记。"""
import datetime
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core import api, connect
from core.metrics import biz_day

ui.page("收银", "🧾")
ui.guard()

st.title("收银台")
day = biz_day()

skus = {r["barcode"]: dict(r) for r in connect().execute(
    "SELECT sku_id, barcode, name, spec, category, price FROM sku "
    "WHERE barcode IS NOT NULL")}
names = {r["sku_id"]: dict(r) for r in connect().execute(
    "SELECT sku_id, name, spec, price FROM sku")}

cart = st.session_state.setdefault("pos_cart", {})
n = st.session_state.setdefault("scan_n", 0)

st.caption(f"业务日 {day}　单价取商品档案，改价请到设置页")
raw = st.text_area("扫码区", height=110, key=f"scan_box_{n}",
                   placeholder="连续扫码，每行一个码", label_visibility="collapsed")

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    if st.button("加入本单", type="primary", width="stretch"):
        codes = [ln.strip().upper() for ln in raw.splitlines() if ln.strip()]
        unknown = []
        for code in codes:
            row = skus.get(code)
            if row is None:
                unknown.append(code)
                continue
            cart[row["sku_id"]] = cart.get(row["sku_id"], 0) + 1
        if unknown:
            st.error("未识别：" + "、".join(unknown))
        if codes and len(codes) > len(unknown):
            st.session_state["scan_n"] = n + 1
            st.rerun()
with c2:
    if st.button("清空", width="stretch"):
        st.session_state["pos_cart"] = {}
        st.rerun()
with c3:
    st.caption(f"本单 {sum(cart.values())} 件")

if cart:
    body, total = [], 0.0
    for sku_id, qty in cart.items():
        row = names[sku_id]
        amount = qty * float(row["price"])
        total += amount
        body.append({"品名": row["name"], "规格": row["spec"] or "—",
                     "单价": float(row["price"]), "数量": qty, "小计": round(amount, 2)})
    st.dataframe([{**b, "单价": f"¥{b['单价']:.2f}", "小计": f"¥{b['小计']:.2f}"} for b in body],
                 width="stretch", hide_index=True)
    c1, c2 = st.columns([3, 1])
    c1.metric("合计", f"¥{total:.2f}", label_visibility="visible")
    with c2:
        if st.button("结账", type="primary", width="stretch"):
            hour = max(9, min(21, datetime.datetime.now().hour))
            res = api.checkout([(k, v) for k, v in cart.items()], hour)
            st.session_state["pos_flash"] = {
                "msg": f"已结账　{res['items']} 件　¥{res['amount']:.2f}",
                "lines": body,
            }
            st.session_state["pos_cart"] = {}
            st.rerun()

flash = st.session_state.pop("pos_flash", None)
if flash:
    st.success(flash["msg"])
    st.dataframe([{**b, "单价": f"¥{b['单价']:.2f}", "小计": f"¥{b['小计']:.2f}"}
                  for b in flash["lines"]], width="stretch", hide_index=True)

st.divider()

st.subheader("售罄标记")
with st.form("soldout"):
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        pick = st.selectbox("品类", [f"{k} {v['name']}" for k, v in
                                   sorted(names.items())], label_visibility="collapsed")
    with c2:
        hour = st.number_input("售罄时刻", 9, 21, 15, label_visibility="collapsed")
    with c3:
        if st.form_submit_button("标记售罄", width="stretch"):
            sku_id = pick.split()[0]
            api.record_soldout(sku_id, int(hour))
            st.success(f"{names[sku_id]['name']} 记为 {int(hour)}:00 售罄")

# ---------------------------------------------------------------- 台账登记
st.divider()
with st.expander("台账登记　补录销量 / 到货 / 报损 / 盘点"):
    sku_all = [dict(r) for r in connect().execute(
        "SELECT sku_id, name, spec FROM sku ORDER BY sku_id")]
    labels = {f"{r['sku_id']} {r['name']}" + (f" {r['spec']}" if r["spec"] else ""): r["sku_id"]
              for r in sku_all}
    default = st.session_state.get("sku_id", sku_all[0]["sku_id"])
    idx = next((i for i, v in enumerate(labels.values()) if v == default), 0)

    t1, t2, t3, t4 = st.tabs(["补录销量", "到货登记", "报损登记", "盘点校正"])
    with t1:
        with st.form("sale"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="x_sku")
            qty = st.number_input("件数", 1, 999, 5)
            when = st.slider("时段", 9, 21, 14)
            if st.form_submit_button("记录", width="stretch"):
                r = api.record_sale(labels[pick], int(qty), int(when))
                st.success(f"{pick.split()[1]} 当日累计 {r['total']} 件")
    with t2:
        pend = api.pending_arrivals(day) or api.pending_arrivals()
        if pend:
            keys = [f"{x['name']}　应到 {x['qty']} 件　{x['day']}" for x in pend]
            with st.form("arrival"):
                pick = st.selectbox("在途单", keys, key="a_pick")
                it = pend[keys.index(pick)]
                qty = st.number_input("实收数量", 0, 999, it["qty"])
                if st.form_submit_button("确认到货", width="stretch"):
                    r = api.record_arrival(it["sku_id"], int(qty), day=it["day"])
                    if r["diff"]:
                        st.warning(f"{it['name']} 应到 {r['expected']}，实收 {qty}，"
                                   f"差 {r['diff']:+d} 件（已留痕）")
                    else:
                        st.success(f"{it['name']} 到货 {qty} 件")
        else:
            with st.form("arrival"):
                pick = st.selectbox("商品", list(labels.keys()), index=idx, key="a_sku")
                qty = st.number_input("实收数量", 0, 999, 30)
                if st.form_submit_button("确认到货", width="stretch"):
                    r = api.record_arrival(labels[pick], int(qty))
                    nm = pick.split()[1]
                    if r["diff"]:
                        st.warning(f"{nm} 应到 {r['expected']}，实收 {qty}，差 {r['diff']:+d} 件")
                    else:
                        st.success(f"{nm} 到货 {qty} 件")
    with t3:
        with st.form("waste"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="w_sku")
            qty = st.number_input("报废件数", 1, 99, 2)
            if st.form_submit_button("登记报损", width="stretch"):
                api.record_waste(labels[pick], int(qty))
                st.success(f"{pick.split()[1]} 报废 {qty} 件")
    with t4:
        with st.form("count"):
            pick = st.selectbox("商品", list(labels.keys()), index=idx, key="c_sku")
            real = st.number_input("实盘数量", 0, 999, 0)
            if st.form_submit_button("按实盘调平", width="stretch"):
                r = api.record_count(labels[pick], int(real))
                st.success(f"账面 {r['book']} → 实盘 {r['real']}，调整 {r['diff']:+d}")
