# -*- coding: utf-8 -*-
"""给新系统截图。"""
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8505"
OUT = Path(r"D:\dpwenzhang\shop-orders\docs\screens")
OUT.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")
        time.sleep(2)
        page.locator("input").nth(0).fill("boss")
        page.locator("input").nth(1).fill("123456")
        page.get_by_role("button", name="登录").click()
        time.sleep(5)

        page.screenshot(path=str(OUT / "01_今日.png"))
        print("今日 ok")

        links = page.locator("[data-testid='stSidebarNav'] a")
        n = links.count()
        print("导航项:", [links.nth(i).inner_text().strip() for i in range(n)])
        for i in range(n):
            name = links.nth(i).inner_text().strip()
            links.nth(i).click()
            time.sleep(3)
            page.screenshot(path=str(OUT / f"{i+2:02d}_{name}.png"))
            print(name, "ok")
        b.close()


if __name__ == "__main__":
    main()
