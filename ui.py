# -*- coding: utf-8 -*-
"""页面公共件：登录、角色切换、改密码、格式化。"""
import streamlit as st

from core import connect, auth
from core.metrics import ensure_today, biz_day

ROLE_CN = {"owner": "店主", "clerk": "店员"}
WHICH = {"owner": "店主", "clerk": "店员"}
USERS = {"店主": "boss", "店员": "clerk"}


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
    st.caption("门店订货决策系统")
    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        who = st.radio("登录身份", ["店主", "店员"], horizontal=True)
        with st.form("login"):
            u = st.text_input("账号", value=USERS[who], key=f"login_u_{who}")
            p = st.text_input("密码", type="password", key=f"login_p_{who}")
            if st.form_submit_button("登录", width="stretch"):
                user = auth.check(conn(), u.strip(), p)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("账号或密码不正确")
        st.caption("演示口令：boss / 123456　clerk / 123456。登录后可在侧栏修改。")
    st.stop()


def guard():
    user = login()
    with st.sidebar:
        st.markdown(f"**{user['username']}**　{ROLE_CN[user['role']]}")
        if st.button("切换账号", width="stretch"):
            st.session_state.pop("user", None)
            st.rerun()
        with st.expander("修改密码"):
            with st.form("chpwd"):
                old = st.text_input("原密码", type="password")
                new = st.text_input("新密码（至少 6 位）", type="password")
                if st.form_submit_button("保存", width="stretch"):
                    try:
                        auth.change_password(conn(), user["username"], old, new)
                        st.success("密码已更新")
                    except ValueError as e:
                        st.error(str(e))
    return user


def money(x):
    return f"¥{x:,.0f}"


def need_owner(user, what="该页面"):
    """店员账号进来只看到提示，直接停在页首。"""
    if user.get("role") != "owner":
        st.warning(f"{what}仅店主可用，当前登录为店员。如需查看，请用店主账号登录。")
        st.stop()


def pct(x):
    return f"{x*100:.1f}%"
