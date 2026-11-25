# -*- coding: utf-8 -*-
"""商品档案导入的单元测试。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core
from core import api


class Case(unittest.TestCase):
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

    def parse(self, head, rows):
        body = "\n".join([head] + rows).encode("utf-8")
        p = api.catalog_read(body)
        return api.catalog_check(p["headers"], p["rows"])


HEAD = "编号,品名,分类,规格,来源,进价,售价,处理价,保质期,条码"


class TestCatalog(Case):
    def test_template_is_parsable(self):
        p = api.catalog_read(api.catalog_template())
        self.assertEqual(p["rows"][0][0], "烘焙01")
        self.assertEqual(len(p["guess"]), 10)

    def test_rejects_bad_rows(self):
        checked = self.parse(HEAD, [
            "烘焙09,测试,烘焙,原味,自制,9,8,1,1,",   # 售价低于进价
            "烘焙10,测试,烘焙,原味,自制,5,9,6,1,",   # 处理价不低于进价
            "烘焙11,测试,烘焙,原味,自制,5,9,1,9,",   # 保质期超范围
            "烘焙12,测试,烘焙,原味,外送,5,9,1,1,",   # 来源不认识
            "烘焙13,测试,烘焙,原味,自制,5,9,1,1,",
            "烘焙13,重复,烘焙,原味,自制,5,9,1,1,",   # 文件内重复
        ])
        self.assertEqual(len(checked["ok"]), 1)
        self.assertEqual(len(checked["bad"]), 5)
        reasons = " ".join(b["reason"] for b in checked["bad"])
        self.assertIn("售价必须高于进价", reasons)
        self.assertIn("处理价", reasons)
        self.assertIn("保质期", reasons)
        self.assertIn("来源", reasons)
        self.assertIn("重复", reasons)

    def test_commit_updates_and_creates(self):
        checked = self.parse(HEAD, [
            "烘焙01,吐司,烘焙,原味,自制,5.5,12.5,2.5,1,SH201",   # 已有：改价
            "烘焙21,新品可颂,烘焙,巧克力,自制,6.0,13.0,0,1,",     # 新增：自动条码
        ])
        self.assertEqual(len(checked["ok"]), 2)
        res = api.catalog_commit(checked["ok"])
        self.assertEqual((res["created"], res["updated"]), (1, 1))

        old = self.conn.execute(
            "SELECT price, spec FROM sku WHERE sku_id='烘焙01'").fetchone()
        self.assertAlmostEqual(old["price"], 12.5, places=2)
        self.assertEqual(old["spec"], "原味")

        new = self.conn.execute(
            "SELECT barcode, mu, sigma, source FROM sku WHERE sku_id='烘焙21'").fetchone()
        self.assertTrue(new["barcode"].startswith("SH2"))
        self.assertEqual(new["mu"], 0)
        self.assertEqual(new["sigma"], 0)
        self.assertEqual(new["source"], "自制")

    def test_barcode_conflict_falls_back(self):
        checked = self.parse(HEAD, [
            "新1,占码,烘焙,原味,自制,5,9,0,1,SH201",   # SH201 已被吐司占用
        ])
        api.catalog_commit(checked["ok"])
        row = self.conn.execute(
            "SELECT barcode FROM sku WHERE sku_id='新1'").fetchone()
        self.assertNotEqual(row["barcode"], "SH201")
        n = self.conn.execute(
            "SELECT COUNT(*) FROM sku WHERE barcode=?", (row["barcode"],)).fetchone()[0]
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
