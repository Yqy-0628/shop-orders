# -*- coding: utf-8 -*-
"""契约自检：确认每个函数的返回形状符合约定。B 的页面就靠这个写。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import api

ok = True


def check(name, obj, keys):
    global ok
    if isinstance(obj, list):
        obj = obj[0] if obj else {}
    missing = [k for k in keys if k not in obj]
    flag = "OK " if not missing else "ERR"
    if missing:
        ok = False
    print(f"[{flag}] {name:<16} 缺字段: {missing if missing else '无'}")


first = api._skus(api.connect())[0]["sku_id"] if api._skus(api.connect()) else "饮品01"

check("data_issues", api.data_issues(), ["code", "sku_id", "message", "severity"])
check("today_tasks", api.today_tasks(), ["sku_id", "type", "title", "detail"])
check("predict", api.predict(first), ["value", "lo", "hi", "level", "explain"])
check("suggest", api.suggest(first), ["tiers", "recommend"])
check("scoreboard", api.scoreboard(), ["follow", "ignore", "delta"])
check("day_review", api.day_review(), ["predicted", "actual", "kind"])
check("auto_lines", api.auto_lines(), ["sku_id", "qty"])
check("record_decision", api.record_decision(first, 34, "天气"),
      ["ok", "qty", "reason"])

print()
print("predict 示例：")
print(json.dumps(api.predict(first), ensure_ascii=False, indent=2))
print()
print("suggest 示例：")
print(json.dumps(api.suggest(first)["tiers"], ensure_ascii=False, indent=2))

print("\n" + ("全部符合契约" if ok else "有字段缺失，页面层别开工"))
