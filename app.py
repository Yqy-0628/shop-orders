# -*- coding: utf-8 -*-
"""入口：登录后直接进「今日」。"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ui

ui.page("该订多少", "📦")
ui.guard()

st.title("该订多少")
st.caption("门店订货决策系统")

try:
    st.switch_page("pages/1_今日.py")
except Exception:
    st.page_link("pages/1_今日.py", label="进入今日", icon="☀️")
    st.page_link("pages/2_订货.py", label="去订货", icon="📦")
    st.page_link("pages/4_复盘.py", label="看复盘", icon="🔁")
