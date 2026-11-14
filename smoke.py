# -*- coding: utf-8 -*-
"""五个新页面逐页跑一遍，抓异常。"""
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent
FILES = ["app.py"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pages").glob("*.py"))

ok = True
for f in FILES:
    at = AppTest.from_file(str(ROOT / f), default_timeout=90)
    at.session_state["user"] = {"username": "boss", "role": "owner"}
    at.run()
    bad = len(at.exception)
    print(f"[{'OK ' if not bad else 'ERR'}] {f}")
    if bad:
        ok = False
        for e in at.exception:
            print("     ", e.message)

print("\n全部通过" if ok else "\n有页面报错")
sys.exit(0 if ok else 1)
