# -*- coding: utf-8 -*-
"""演示用的完整一日排练：订货 → 到货 → 收银 → 售罄 → 报损 → 收工账。

不碰界面，直接走 core.api，用来在答辩前确认整条链路能跑通。
跑完会把当天写进去的流水（销售、售罄、到货、报损）撤掉，只留下订货决策与在途单，
业务日仍停在原来的那天，所以看板和 28 天复盘的数字不会被改。

    python scripts/demo_flow.py --day 2026-11-10
    python scripts/demo_flow.py --day 2026-11-10 --reset
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import api, connect, metrics   # noqa: E402


def _q(sql, *a):
    conn = connect()
    try:
        return conn.execute(sql, a).fetchone()[0]
    finally:
        conn.close()


def state(tag):
    print(f"--- {tag}")
    print(f"    业务日        {metrics.biz_day()}")
    print(f"    订货留痕      {_q('SELECT COUNT(*) FROM decision_log')} 条")
    print(f"    在途入库      {_q(chr(83)+'ELECT COUNT(*) FROM stock_move WHERE status=? ', '在途')} 条")
    print(f"    已到货入库    {_q(chr(83)+'ELECT COUNT(*) FROM stock_move WHERE status=? ', '已到货')} 条")


def reset(day):
    """撤掉演练当天写入的流水，只保留 decision_log，并把订货量还原成在途单。"""
    conn = connect()
    logs = conn.execute(
        "SELECT sku_id, adopted_qty, params_json FROM decision_log "
        "WHERE json_extract(params_json, '$.target_day')=?", (day,)).fetchall()
    kept = [(r["sku_id"], r["adopted_qty"] or 0) for r in logs if (r["adopted_qty"] or 0) > 0]

    conn.execute("DELETE FROM sales WHERE day=?", (day,))
    conn.execute("DELETE FROM stockout_mark WHERE day=?", (day,))
    conn.execute("DELETE FROM stock_move WHERE day=?", (day,))
    # 到货差异那几条也属于演练痕迹，一并清掉，保留纯订货决策
    conn.execute(
        "DELETE FROM decision_log WHERE json_extract(params_json, '$.kind')='arrival_diff' "
        "AND json_extract(params_json, '$.day')=?", (day,))

    for sku_id, qty in kept:
        cost = conn.execute("SELECT cost FROM sku WHERE sku_id=?", (sku_id,)).fetchone()
        if cost is None:
            continue
        conn.execute(
            "INSERT INTO stock_move (sku_id, day, type, qty, unit_cost, status) "
            "VALUES (?,?,'入库',?,?,'在途')",
            (sku_id, day, qty, cost["cost"]))
    conn.commit()
    conn.close()
    print(f"已撤销 {day} 的流水，保留 {len(kept)} 张在途进货单")


def rehearse(day):
    state("演练开始")
    ol = api.order_list(day)
    sm = ol["summary"]
    print(f"备货清单：进货 {sm['purchase_kinds']} 个品类 {sm['purchase_qty']} 件 / "
          f"自制 {sm['make_kinds']} 个品类 {sm['make_qty']} 件 / 供货商 {sm['suppliers']} 家")

    picks = ol["purchase"][:6] + ol["make"][:4]
    changed = {picks[3]["sku_id"]: ("天气", max(1, picks[3]["qty"] - 4)),
               picks[7]["sku_id"]: ("经验", picks[7]["qty"] + 5)}

    n_ok = 0
    for it in picks:
        sku, qty = it["sku_id"], it["qty"]
        reason = None
        if sku in changed:
            reason, qty = changed[sku]
        r = api.record_decision(sku, qty, reason, day=day)
        n_ok += 1
        note = f"（{reason}，建议 {r['suggested']} → 实订 {qty}）" if reason else ""
        print(f"    登记 {sku} {it['name']:<6} {qty:>3} 件{note}")
    print(f"    订货登记 {n_ok} 条")

    arr = picks[:4]
    for i, it in enumerate(arr):
        recv = it["qty"] - (3 if i == 0 else 0)
        api.record_arrival(it["sku_id"], recv, day=day)
        print(f"    到货 {it['sku_id']} {it['name']} 实收 {recv} 件"
              + ("（少送 3 件，已留痕）" if i == 0 else ""))

    c1 = api.checkout([(arr[0]["sku_id"], 6), (arr[1]["sku_id"], 3)], hour=10, day=day)
    c2 = api.checkout([(arr[2]["sku_id"], 2), (arr[3]["sku_id"], 1)], hour=16, day=day)
    print(f"    结账 2 单：{c1['amount']:.0f} / {c2['amount']:.0f} 元，共 {c1['items'] + c2['items']} 件")

    api.record_soldout(arr[0]["sku_id"], 12, day=day)
    api.record_soldout(arr[1]["sku_id"], 15, day=day)
    print("    售罄标记 2 条（12 点、15 点）")

    api.record_waste(arr[3]["sku_id"], 1, day=day)
    print("    报损 1 件")

    d = api.day_close(day)
    s = d["summary"]
    print(f"    收工账：进 {s['in']} / 卖 {s['sold']} / 损 {s['waste']} / 剩 {s['left']}")
    for t in d["tips"]:
        print(f"    · {t}")

    reset(day)
    state("演练结束（回到演示初始态）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-11-10")
    ap.add_argument("--reset", action="store_true", help="只撤销当天的演练流水")
    a = ap.parse_args()
    if a.reset:
        state("撤销前")
        reset(a.day)
        state("撤销后")
    else:
        rehearse(a.day)


if __name__ == "__main__":
    main()
