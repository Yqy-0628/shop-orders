# -*- coding: utf-8 -*-
"""把 UCI Online Retail 的真实流水，压成「一个 SKU 的日销量」序列。

输出 data/uci_daily.csv（day, qty），作为截断实验的「真实需求」。
"""
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ZIP = DATA / "uci_online_retail.zip"
CSV = DATA / "online_retail.csv"
OUT = DATA / "uci_daily.csv"


def pick_series(df):
    """挑一个日销量稳定、天数够多的 SKU。"""
    days = df.groupby("StockCode")["day"].nunique()
    order = days.sort_values(ascending=False).head(400).index

    best = None
    for code in order:
        s = df[df.StockCode == code].groupby("day")["Quantity"].sum()
        if len(s) < 150:
            continue
        mean, cv = s.mean(), s.std() / max(s.mean(), 1e-9)
        if not (8 <= mean <= 45 and 0.2 <= cv <= 0.9):
            continue
        score = len(s) * (1 - abs(cv - 0.45))
        if best is None or score > best[0]:
            best = (score, code, s, mean, cv)
    return best


def read_any():
    """支持三种来源：压缩包、压缩包里的 csv、直接放的 csv。"""
    if CSV.exists():
        print(f"读取 {CSV.name} ...")
        return pd.read_csv(CSV, encoding="latin-1")

    with zipfile.ZipFile(ZIP) as z:
        name = [n for n in z.namelist() if n.lower().endswith((".xlsx", ".csv"))][0]
        print(f"读取 {name} ...")
        if name.lower().endswith(".csv"):
            return pd.read_csv(z.open(name), encoding="latin-1")
        return pd.read_excel(z.open(name))


def main():
    if not (ZIP.exists() or CSV.exists()):
        print(f"没找到数据。把 online+retail.zip 或 online_retail.csv 放到 {DATA}")
        sys.exit(2)

    df = read_any()

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(subset=["Quantity", "InvoiceDate"])
    df = df[(df["Quantity"] > 0) & (df["UnitPrice"] > 0)].copy()
    df["day"] = pd.to_datetime(df["InvoiceDate"]).dt.date
    print(f"清洗后 {len(df):,} 行，{df.StockCode.nunique()} 个商品，"
          f"{df.day.min()} ~ {df.day.max()}")

    best = pick_series(df)
    if not best:
        print("没有找到合适的 SKU，放宽条件再试")
        sys.exit(3)
    _, code, s, mean, cv = best

    full = pd.date_range(s.index.min(), s.index.max(), freq="D").date
    s = s.reindex(full, fill_value=0)
    s.index.name = "day"
    s.name = "qty"
    s.reset_index().to_csv(OUT, index=False)

    print(f"\n选中 {code}：{len(s)} 天，日均 {mean:.1f} 件，变异系数 {cv:.2f}")
    zero = (s == 0).mean() * 100
    print(f"零销量天数 {(s == 0).sum()}（占 {zero:.0f}%）")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
