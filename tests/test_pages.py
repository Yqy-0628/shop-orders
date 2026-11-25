# -*- coding: utf-8 -*-
"""页面级冒烟：用 Streamlit 的 AppTest 把每个页面跑一遍，确认没有异常。

跑法：python -m unittest tests.test_pages -v
不点按钮，只验证首屏渲染（渲染出错通常是最常见的页面故障）。
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("SHOP_DB_MODE", "file")

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["1_今日", "2_订货", "3_记录", "4_复盘", "5_设置",
         "6_看板", "7_收银", "8_标签", "9_导入"]


class TestPages(unittest.TestCase):
    def _run(self, name, role):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(ROOT / "pages" / f"{name}.py"), default_timeout=60)
        at.session_state["user"] = {"username": "boss" if role == "owner" else "clerk",
                                    "role": role}
        at.run()
        self.assertFalse(at.exception, f"{name} 在 {role} 下渲染失败：{at.exception}")

    def test_owner_pages(self):
        for name in PAGES:
            with self.subTest(page=name):
                self._run(name, "owner")

    def test_clerk_pages(self):
        for name in PAGES:
            with self.subTest(page=name):
                self._run(name, "clerk")


if __name__ == "__main__":
    unittest.main()
