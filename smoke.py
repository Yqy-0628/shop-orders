# -*- coding: utf-8 -*-
"""不打开浏览器，直接把每个页面跑一遍，抓异常。"""
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent
FILES = ["app.py"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pages").glob("*.py"))

ok = True
for role, name in [("owner", "boss"), ("clerk", "clerk")]:
    for f in FILES:
        at = AppTest.from_file(str(ROOT / f), default_timeout=60)
        at.session_state["user"] = {"username": name, "role": role}
        at.run()
        bad = len(at.exception)
        status = "OK " if bad == 0 else "ERR"
        print(f"[{status}] {role:5s} {f}")
        if bad:
            ok = False
            for e in at.exception:
                print("     ", e.message)

print("\n全部通过" if ok else "\n有页面报错")
sys.exit(0 if ok else 1)
