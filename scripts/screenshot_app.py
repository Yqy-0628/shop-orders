# -*- coding: utf-8 -*-
"""用已安装的 Edge 驱动一个真浏览器，登录后逐页截图。"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8504"
OUT = Path(r"D:\dpwenzhang\shop-orders\docs\screens")
OUT.mkdir(parents=True, exist_ok=True)


def login(page, user="boss"):
    page.goto(BASE, wait_until="networkidle")
    time.sleep(2)
    inputs = page.locator("input")
    inputs.nth(0).fill(user)
    inputs.nth(1).fill("123456")
    page.get_by_role("button", name="登录").click()
    time.sleep(3)


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    print("  ->", name)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        login(page)
        shot(page, "00_首页")

        # 侧边栏里的页面链接
        links = page.locator("nav a, [data-testid='stSidebarNav'] a")
        n = links.count()
        print("侧边栏链接数:", n)
        names = []
        for i in range(n):
            names.append(links.nth(i).inner_text().strip())
        print("页面:", names)

        for i, nm in enumerate(names):
            try:
                links.nth(i).click()
                time.sleep(4.5)
                shot(page, f"{i+1:02d}_{nm}")
            except Exception as e:
                print("  跳过", nm, e)

        b.close()


if __name__ == "__main__":
    main()
