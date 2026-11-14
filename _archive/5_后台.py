# -*- coding: utf-8 -*-
"""后台：角色、决策日志、数据概览。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui
from core.metrics import DEMO_TODAY

ui.page("后台", "⚙️")
user = ui.guard()
conn = ui.conn()

st.title("⚙️ 后台")
st.caption(f"当前身份：{ui.ROLE_CN[user['role']]}（{user['username']}）")

st.subheader("账号")
users = conn.execute("SELECT username, role FROM app_user").fetchall()
st.dataframe([{"账号": u["username"], "角色": ui.ROLE_CN[u["role"]]} for u in users],
             width="stretch", hide_index=True)
st.info("用 clerk / 123456 在另一个标签页登录，再回收银台看：进价和毛利都不见了。")

st.divider()
st.subheader("决策日志")
logs = conn.execute(
    """SELECT ts, username, sku_id, q_star, adopted_qty, adopted
       FROM decision_log ORDER BY id DESC LIMIT 20"""
).fetchall()
if logs:
    st.dataframe(
        [{"时间": r["ts"], "谁": r["username"] or "-", "商品": r["sku_id"],
          "建议量": r["q_star"], "实际订": r["adopted_qty"] or "-",
          "采纳": "是" if r["adopted"] else "否"} for r in logs],
        width="stretch", hide_index=True,
    )
    total = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
    adopt = conn.execute("SELECT COUNT(*) FROM decision_log WHERE adopted=1").fetchone()[0]
    if total:
        st.metric("建议采纳率", f"{adopt/total*100:.0f}%",
                  help="系统建议了多少次、真正照着订了多少次——信任是有数字的")
else:
    st.caption("还没有决策记录。去决策台点一次“生成订货单”。")

st.divider()
st.subheader("数据规模")
c1, c2, c3, c4 = st.columns(4)
c1.metric("SKU", conn.execute("SELECT COUNT(*) FROM sku").fetchone()[0])
c2.metric("销售记录", conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0])
c3.metric("售罄标记", conn.execute("SELECT COUNT(*) FROM stockout_mark").fetchone()[0])
c4.metric("实物变动", conn.execute("SELECT COUNT(*) FROM stock_move").fetchone()[0])
st.caption(f"演示日期 {DEMO_TODAY}　·　数据为参数化仿真，参数见 verify.py")
