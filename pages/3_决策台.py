# -*- coding: utf-8 -*-
"""决策台：三个滑块，一条曲线，一个建议。"""
import datetime as dt
import sys
from pathlib import Path
from statistics import NormalDist

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.metrics import stock_rows, DEMO_TODAY
from core.auth import can_see_cost
from core.replay import replay_day

ui.page("决策台", "🎛️")
user = ui.guard()
conn = ui.conn()
show_cost = can_see_cost(user["role"])

st.title("🎛️ 该订多少")
st.caption("改一个参数，看建议怎么变——规则变了，决策就变")

skus = conn.execute("SELECT * FROM sku ORDER BY category, sku_id").fetchall()
labels = [f"{s['sku_id']} {s['name']}" for s in skus]
idx = next((i for i, s in enumerate(skus) if s["name"] == "鲜奶茶"), 0)
pick = st.selectbox("选一个商品", labels, index=idx)
s = next(x for x in skus if f"{x['sku_id']} {x['name']}" == pick)

margin = s["price"] - s["cost"]
row = next((r for r in stock_rows(conn, DEMO_TODAY) if r["sku_id"] == s["sku_id"]), None)
stock = row["qty"] if row else 0
incoming = row["incoming"] if row else 0

c1, c2, c3 = st.columns(3)
with c1:
    salvage_rate = st.slider("残值率（卖不掉能收回成本的几成）", 0, 100,
                             int(round(s["salvage"] / s["cost"] * 100)), 5,
                             help="0% = 直接扔掉；80% = 打八折清货")
with c2:
    cu = st.slider("缺货代价（少卖一件少赚多少）", 0.0, round(margin * 2, 1),
                   round(margin, 1), 0.5)
with c3:
    target = st.slider("如果我要做到的服务水平", 50, 99, 95, 1, help="看看代价有多大")

salvage = s["cost"] * salvage_rate / 100
co = max(0.01, s["cost"] - salvage)
cr = cu / (cu + co)
z = NormalDist().inv_cdf(cr)
q = s["mu"] + z * s["sigma"]

# 净订货量：扣掉已有库存和在途，避免重复下单
net = max(0.0, q - stock - incoming)

z_t = NormalDist().inv_cdf(target / 100)
q_t = s["mu"] + z_t * s["sigma"]

a, b, c, d = st.columns(4)
a.metric("临界比", f"{cr:.3f}", help="Cu / (Cu + Co)")
b.metric("对应服务水平", f"{cr*100:.0f}%")
c.metric("理论最优量", f"{q:.0f} 件", help="μ + z·σ")
d.metric("本次应订", f"{net:.0f} 件", delta=f"库存 {stock:.0f} + 在途 {incoming:.0f}",
         delta_color="off")

if incoming > 0:
    st.warning(f"已有一张在途订单 {incoming:.0f} 件，今天的建议已扣掉它，不会重复下单。")

st.divider()
left, right = st.columns([1.1, 1])

with left:
    st.subheader("服务水平 ↔ 订货量")
    curve = [{"服务水平": p,
              "需要订多少": s["mu"] + NormalDist().inv_cdf(p / 100) * s["sigma"]}
             for p in range(50, 100)]
    st.line_chart(curve, x="服务水平", y="需要订多少", height=300)
    q95 = s["mu"] + NormalDist().inv_cdf(0.95) * s["sigma"]
    st.caption(f"μ = {s['mu']:.1f}，σ = {s['sigma']:.1f}。"
               f"从 95% 到 99%，订货量要多 {q_t - q95:.0f} 件——最后几个点最贵。")
    if show_cost:
        st.caption(f"进价 {s['cost']} / 售价 {s['price']} / 残值 {salvage:.2f}"
                   f"　→　Cu={cu:.1f}，Co={co:.2f}")

with right:
    st.subheader("那几天发生了什么")
    days = conn.execute(
        "SELECT DISTINCT day FROM stockout_mark WHERE sku_id=? ORDER BY day DESC LIMIT 8",
        (s["sku_id"],),
    ).fetchall()
    if days:
        day = st.selectbox("选一天", [d["day"] for d in days])
        extra = st.slider("如果那天多订几件", 0, 20, 5)
        r = replay_day(conn, s["sku_id"], day, extra)
        st.markdown(
            f"""
那天卖了 **{r['sold_before']:.0f}** 件，但还有 **{r['gap']:.0f}** 件的需求没被满足。
多订 **{extra}** 件 → 能多卖 **{r['recovered']:.0f}** 件，挽回 **{ui.money(r['recovered'] * r['margin'])}**。
"""
        )
        st.metric("当天损失", ui.money(r["lost_before"]),
                  delta=f"−{ui.money(r['lost_before'] - r['lost_after'])}",
                  delta_color="inverse")
    else:
        st.info("这个商品没有售罄记录")

st.divider()
if st.button(f"按建议下单（在途 {net:.0f} 件）", type="primary"):
    tomorrow = (dt.date.fromisoformat(DEMO_TODAY) + dt.timedelta(days=1)).isoformat()
    qty = int(round(net))
    if qty <= 0:
        st.info("库存和在途已经够了，今天不用订。")
    else:
        conn.execute(
            "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
            "VALUES (?,?,'入库',?,?,'在途')",
            (s["sku_id"], tomorrow, qty, s["cost"]),
        )
        conn.execute(
            "INSERT INTO decision_log (ts, username, sku_id, params_json, q_star, "
            "adopted_qty, adopted) VALUES (?,?,?,?,?,?,1)",
            (dt.datetime.now().isoformat(timespec="seconds"), user["username"],
             s["sku_id"], f'{{"salvage_rate":{salvage_rate},"cu":{cu}}}', round(q, 1), qty),
        )
        conn.commit()
        st.success(f"已下单：{s['sku_id']} × {qty}，{tomorrow} 到货（状态：在途）")
