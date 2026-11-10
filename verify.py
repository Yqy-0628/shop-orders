# -*- coding: utf-8 -*-
"""核算：把三个数字算出来。

跑法：python verify.py
"""
from core import connect
from core import order as O
from core import demand as D
from core.metrics import kpi as KPI


def main():
    conn = connect()
    rates = D.hourly_rates(conn)
    skus = [dict(r) for r in conn.execute(
        "SELECT * FROM sku ORDER BY category, sku_id")]

    print("=" * 78)
    print("① 报童模型：每个 SKU 该订多少")
    print("=" * 78)
    print(f"{'SKU':<7}{'品名':<7}{'售价':>6}{'进价':>6}{'残值':>6}"
          f"{'Cu':>5}{'Co':>5}{'临界比':>7}{'服务水平':>7}{'μ':>6}{'Q*':>7}")
    for s in skus:
        cu, co = O.costs(s["cost"], s["price"], s["salvage"])
        cr = O.critical_ratio(cu, co)
        q = O.q_star(s["mu"], s["sigma"], s["cost"], s["price"], s["salvage"])
        flag = "  ← 主推款" if (s["sku_id"].startswith("饮") and s["name"] == "鲜奶茶") else ""
        print(f"{s['sku_id']:<7}{s['name']:<7}{s['price']:>6.1f}{s['cost']:>6.1f}"
              f"{s['salvage']:>6.1f}{cu:>5.1f}{co:>5.1f}{cr:>7.3f}{cr*100:>6.0f}%"
              f"{s['mu']:>6.1f}{q:>7.1f}{flag}")

    perish = {s["sku_id"] for s in skus if s["shelf_life_days"] == 1}

    so_loss_all = so_loss_per = 0.0
    so_hours = 0
    by_sku = {s["sku_id"]: s for s in skus}
    for r in conn.execute("SELECT sku_id, day, start_hour, end_hour FROM stockout_mark"):
        miss = D.missing_hours(r["start_hour"], r["end_hour"])
        wd = conn.execute("SELECT weekday FROM sales WHERE sku_id=? AND day=? LIMIT 1",
                          (r["sku_id"], r["day"])).fetchone()
        if not wd:
            continue
        rate = rates.get((r["sku_id"], wd["weekday"]), 0.0)
        s = by_sku[r["sku_id"]]
        loss = miss * rate * (s["price"] - s["cost"])
        so_loss_all += loss
        so_hours += miss
        if r["sku_id"] in perish:
            so_loss_per += loss

    sp_loss = 0.0
    sp_qty = 0
    for r in conn.execute(
        "SELECT m.qty, s.cost FROM stock_move m JOIN sku s ON s.sku_id=m.sku_id "
        "WHERE m.type='报损'"
    ):
        sp_qty += abs(r["qty"])
        sp_loss += abs(r["qty"]) * r["cost"]
    in_qty = conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM stock_move WHERE type='入库'"
    ).fetchone()[0]

    days = conn.execute("SELECT COUNT(DISTINCT day) FROM sales").fetchone()[0]
    total_hours = days * (D.CLOSE_H - D.OPEN_H) * len(skus)

    print()
    print("=" * 78)
    print(f"② 84 天发生了什么（{days} 天 × {len(skus)} 个 SKU）")
    print("=" * 78)
    k = KPI(conn)
    print(f"  缺货时长            {so_hours:>8.0f} 小时      缺货率 {k['stockout_rate']*100:>5.1f}%")
    print(f"  报损件数（有记录）  {sp_qty:>8.0f} 件        报损率 {k['spoilage_rate']*100:>5.1f}%")
    print(f"  缺货损失（全部）    {so_loss_all:>8.0f} 元")
    print(f"  缺货损失（易损品）  {so_loss_per:>8.0f} 元")
    print(f"  报损损失（有记录）  {sp_loss:>8.0f} 元")
    print(f"  ── 同一批易损品：缺货 / 报损 = {so_loss_per/sp_loss:>5.2f} 倍")
    print()
    print("  报损是 stock_move 里 type='报损' 的记录，不是从“进货−销售”倒推的。")


if __name__ == "__main__":
    main()
