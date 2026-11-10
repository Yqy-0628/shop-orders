# -*- coding: utf-8 -*-
"""页面公共件：登录、连接、格式化。"""
import streamlit as st

from core import connect, auth
from core.metrics import ensure_today, DEMO_TODAY

ROLE_CN = {"owner": "店主", "clerk": "店员"}


def page(title, icon="📦"):
    st.set_page_config(page_title=f"{title} · 该订多少", page_icon=icon, layout="wide")


def conn():
    if "conn" not in st.session_state:
        c = connect()
        ensure_today(c)
        st.session_state.conn = c
    return st.session_state.conn


def login():
    """没有登录态就渲染登录框，并停在这里。"""
    if st.session_state.get("user"):
        return st.session_state["user"]

    st.title("📦 该订多少")
    st.caption("小店订货决策台 · 演示环境")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        with st.form("login"):
            u = st.text_input("账号", value="boss")
            p = st.text_input("密码", type="password", value="123456")
            if st.form_submit_button("登录", width="stretch"):
                user = auth.check(conn(), u.strip(), p)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("账号或密码不对")
        st.info("演示账号：boss / 123456（店主）　clerk / 123456（店员）")
    st.stop()


def guard():
    user = login()
    with st.sidebar:
        st.markdown(f"**{user['username']}** · {ROLE_CN[user['role']]}")
        if st.button("退出", width="stretch"):
            st.session_state.pop("user", None)
            st.rerun()
    return user


def money(x):
    return f"¥{x:,.0f}"


def pct(x):
    return f"{x*100:.1f}%"
