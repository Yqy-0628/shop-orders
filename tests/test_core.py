# -*- coding: utf-8 -*-
"""核心逻辑单元测试。

跑法：python -m unittest discover -s tests -v
每个用例用一份数据库副本，测完删掉，不碰 data/shop.db。
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core
from core import api, metrics, pipeline, importer


class ShopCase(unittest.TestCase):
    """公共夹具：临时库 + 常用查询。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.db = self.dir / "shop.db"
        shutil.copy2(ROOT / "data" / "shop.db", self.db)
        self._old = core.DB_PATH
        core.DB_PATH = self.db
        self.conn = core.connect()

    def tearDown(self):
        self.conn.close()
        core.DB_PATH = self._old
        shutil.rmtree(self.dir, ignore_errors=True)

    def any_sku(self):
        return self.conn.execute(
            "SELECT sku_id FROM sku ORDER BY sku_id LIMIT 1").fetchone()["sku_id"]

    def sku_with_stockout(self):
        return self.conn.execute(
            "SELECT sku_id FROM stockout_mark GROUP BY sku_id "
            "ORDER BY COUNT(*) DESC LIMIT 1").fetchone()["sku_id"]

    def book(self, sku, day):
        for r in metrics.stock_rows(self.conn, day):
            if r["sku_id"] == sku:
                return r["qty"]
        return 0


class TestBizDay(ShopCase):
    """业务日：跟着数据走，不受记账影响。"""

    def test_follows_data_and_env(self):
        last = self.conn.execute(
            "SELECT MAX(day) FROM stock_move WHERE status='已到货'").fetchone()[0]
        self.assertEqual(metrics.biz_day(self.conn), last)

        os.environ["SHOP_BIZ_DAY"] = "2027-01-01"
        try:
            self.assertEqual(metrics.biz_day(self.conn), "2027-01-01")
        finally:
            os.environ.pop("SHOP_BIZ_DAY", None)

    def test_sale_does_not_move_biz_day(self):
        day = metrics.biz_day(self.conn)
        api.record_sale(self.any_sku(), 3, 12, day)
        self.assertEqual(metrics.biz_day(self.conn), day)


class TestFillDemand(ShopCase):
    """补齐：卖光那天的销量是下限，要按缺货时长把需求补回来。"""

    def test_soldout_days_are_restored(self):
        sku = self.sku_with_stockout()
        df = pipeline.load_daily(self.conn, sku)
        rate = pipeline.hourly_rate(self.conn, sku)
        self.assertGreater(rate, 0)

        filled = pipeline.fill_demand(df, rate)
        soldout = filled[filled["soldout"]]
        self.assertGreater(len(soldout), 0)
        self.assertTrue((soldout["demand"] > soldout["sold"]).all())

        normal = filled[~filled["soldout"]]
        self.assertTrue((normal["demand"] == normal["sold"]).all())


class TestTiers(ShopCase):
    """三档建议：数量递增、代价齐全、合计等于两笔相加。"""

    def test_ordered_and_costed(self):
        sku = self.any_sku()
        day = metrics.biz_day(self.conn)
        weekday = dt.date.fromisoformat(day).weekday()
        out = pipeline.suggest_sku(sku, weekday, self.conn)["tiers"]

        self.assertEqual([t["key"] for t in out], ["save", "normal", "safe"])
        qty = [t["qty"] for t in out]
        self.assertTrue(all(qty[i] <= qty[i + 1] for i in range(len(qty) - 1)))

        for t in out:
            for k in ("waste", "short", "waste_cost", "short_cost", "cost_total"):
                self.assertIn(k, t)
            self.assertAlmostEqual(t["cost_total"],
                                   t["waste_cost"] + t["short_cost"], places=1)

        # 订得越多，预期断货的件数不应增加
        self.assertLessEqual(out[2]["short"], out[0]["short"])


class TestRecording(ShopCase):
    """录入：销量累加不覆盖，盘点能把账调平且可重复执行。"""

    def test_sale_accumulates(self):
        sku = self.any_sku()
        day = metrics.biz_day(self.conn)
        base = self.conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM sales WHERE sku_id=? AND day=?",
            (sku, day)).fetchone()[0]
        api.record_sale(sku, 4, 11, day)
        r = api.record_sale(sku, 6, 15, day)
        self.assertEqual(r["day"], day)
        self.assertEqual(r["total"], base + 10)

    def test_count_reconciles_and_is_idempotent(self):
        sku = self.any_sku()
        day = metrics.biz_day(self.conn)
        before = self.book(sku, day)
        target = max(0, before - 3)

        r = api.record_count(sku, target, day)
        self.assertEqual(self.book(sku, day), target)
        self.assertEqual(r["diff"], target - before)

        sql = ("SELECT COUNT(*) FROM stock_move "
               "WHERE type='盘点' AND day=? AND sku_id=?")
        n0 = self.conn.execute(sql, (day, sku)).fetchone()[0]
        api.record_count(sku, target, day)
        n1 = self.conn.execute(sql, (day, sku)).fetchone()[0]
        self.assertEqual(n0, n1)


class TestOptimum(ShopCase):
    """报童最优量：与 μ、σ、临界比的关系必须自洽。"""

    def _opt(self, sku):
        day = metrics.biz_day(self.conn)
        wd = dt.datetime.strptime(day, "%Y-%m-%d").weekday()
        return pipeline.suggest_sku(sku, wd, self.conn)["optimum"]

    def test_above_mean_when_stockout_costs_more(self):
        opt = self._opt(self.any_sku())
        self.assertIsNotNone(opt)
        # 毛利高于过剩损失时临界比超过一半，最优量应高于均值
        self.assertGreater(opt["cr"], 0.5)
        self.assertGreater(opt["qty"], opt["mu"])

    def test_matches_formula(self):
        from core.order import q_star, service_level

        sku = self.any_sku()
        opt = self._opt(sku)
        row = self.conn.execute(
            "SELECT cost, price, salvage FROM sku WHERE sku_id=?", (sku,)).fetchone()
        expect = max(1, round(q_star(opt["mu"], opt["sigma"],
                                     row["cost"], row["price"], row["salvage"])))
        self.assertEqual(opt["qty"], expect)
        self.assertAlmostEqual(opt["cr"], round(
            service_level(row["cost"], row["price"], row["salvage"]), 3))


class TestUpdateSku(ShopCase):
    """商品档案可改，且拒绝会算错临界比的参数。"""

    def test_updates_price(self):
        sku = self.any_sku()
        old = self.conn.execute(
            "SELECT price FROM sku WHERE sku_id=?", (sku,)).fetchone()[0]
        api.update_sku(sku, price=old + 1)
        new = self.conn.execute(
            "SELECT price FROM sku WHERE sku_id=?", (sku,)).fetchone()[0]
        self.assertAlmostEqual(new, old + 1, places=6)

    def test_rejects_bad_prices(self):
        sku = self.any_sku()
        with self.assertRaises(ValueError):
            api.update_sku(sku, cost=999.0)
        with self.assertRaises(ValueError):
            api.update_sku(sku, salvage=999.0)
        with self.assertRaises(ValueError):
            api.update_sku(sku, shelf_life_days=0)


class TestArrival(ShopCase):
    """到货：少送了要留痕，数量以实收为准。"""

    def test_gap_between_order_and_receipt(self):
        sku = self.any_sku()
        day = metrics.biz_day(self.conn)
        self.conn.execute(
            "DELETE FROM stock_move WHERE sku_id=? AND day=?", (sku, day))
        self.conn.commit()

        api.record_decision(sku, 30, None, day)
        r = api.record_arrival(sku, 25, day)
        self.assertEqual(r["expected"], 30)
        self.assertEqual(r["diff"], -5)

        moves = [dict(x) for x in self.conn.execute(
            "SELECT qty, status FROM stock_move WHERE sku_id=? AND day=?", (sku, day))]
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0]["qty"], 25)
        self.assertEqual(moves[0]["status"], "已到货")

        logs = self.conn.execute(
            "SELECT params_json FROM decision_log WHERE sku_id=? AND ts>=? ",
            (sku, dt.date.today().isoformat())).fetchall()
        self.assertTrue(any("arrival_diff" in x["params_json"] for x in logs))

    def test_no_order_means_no_gap(self):
        sku = self.any_sku()
        day = metrics.biz_day(self.conn)
        self.conn.execute(
            "DELETE FROM stock_move WHERE sku_id=? AND day=?", (sku, day))
        self.conn.commit()
        r = api.record_arrival(sku, 12, day)
        self.assertIsNone(r["expected"])
        self.assertIsNone(r["diff"])


class TestImport(ShopCase):
    """导入：认字段、认单品、拒脏行；写入后销售真的进库。"""

    def test_reads_semicolon_and_gbk(self):
        raw = "日期;单品;数量\n2026-11-10;SH203;26\n".encode("gbk")
        headers, rows = core.importer.read_bytes(raw)
        self.assertEqual(headers, ["日期", "单品", "数量"])
        self.assertEqual(len(rows), 1)

    def test_normalizes_dates(self):
        n = core.importer.norm_day
        for s in ("2026-11-20", "2026/11/20", "20261120", "2026年11月20日",
                  "2026-11-20 08:30", "26-11-20"):
            self.assertEqual(n(s), "2026-11-20", s)
        for s in ("", "乱七八糟", "2026-13-40", "2026-11"):
            self.assertIsNone(n(s), s)

    def test_resolves_sku_three_ways(self):
        skus = core.importer._skus()
        self.assertEqual(core.importer.resolve_sku("SH203", skus)["sku_id"], "烘焙03")
        self.assertEqual(core.importer.resolve_sku("菠萝包", skus)["sku_id"], "烘焙03")
        self.assertIsNone(core.importer.resolve_sku("不存在的东西", skus))

    def test_rejects_dirty_rows(self):
        headers = ["日期", "单品", "数量"]
        rows = [["2026-11-10", "SH203", "26"],
                ["坏日期", "SH203", "10"],
                ["2026-11-10", "没这个货", "10"],
                ["2026-11-10", "SH203", "-3"]]
        mapping = core.importer.guess_map(headers)
        ok, bad = core.importer.check(headers, rows, mapping)
        self.assertEqual(len(ok), 1)
        self.assertEqual(len(bad), 3)

    def test_commit_writes_sales(self):
        self.conn.execute("DELETE FROM sales WHERE day='2026-11-10'")
        self.conn.commit()
        headers = ["日期", "单品", "数量", "单价"]
        rows = [["2026-11-10", "SH203", "26", "11.9"],
                ["2026-11-10", "SH302", "13", ""]]
        mapping = core.importer.guess_map(headers)
        ok, _ = core.importer.check(headers, rows, mapping)
        res = core.importer.commit(ok)

        self.assertEqual(res["rows"], 2)
        self.assertEqual(res["units"], 39)
        self.assertEqual(res["skus"], 2)
        got = self.conn.execute(
            "SELECT SUM(qty) FROM sales WHERE day='2026-11-10'").fetchone()[0]
        self.assertEqual(got, 39)

    def test_reconcile_flags_oversell(self):
        sku = "烘焙03"
        day = "2026-11-10"
        opening = self.conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM stock_move "
            "WHERE status='已到货' AND day<? AND sku_id=?", (day, sku)).fetchone()[0]
        core.importer.commit([{"line": 2, "sku_id": sku, "name": "菠萝包",
                               "day": day, "qty": int(opening) + 500,
                               "price": None, "hour": None}])
        rec = core.importer.reconcile(day, day)
        kinds = [i["kind"] for i in rec["issues"] if i["sku_id"] == sku]
        self.assertIn("超卖", kinds)


if __name__ == "__main__":
    unittest.main()
