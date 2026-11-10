# -*- coding: utf-8 -*-
"""给演示地址生成二维码。

用法：
    python scripts/make_qr.py --url http://10.64.126.63:8501
    python scripts/make_qr.py --url https://xxx.streamlit.app --out docs/qr_cloud.png
"""
import argparse
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default=str(ROOT / "docs" / "qr.png"))
    ap.add_argument("--label", default="扫码打开「该订多少」")
    a = ap.parse_args()

    qr = qrcode.QRCode(version=None, box_size=10, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(a.url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1F3864", back_color="white").convert("RGB")

    # 加一条说明和网址，方便现场认
    W = img.width
    pad = 30
    out = Image.new("RGB", (W, img.height + 86), "white")
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    try:
        fb = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 26)
        fr = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 17)
    except OSError:
        fb = fr = ImageFont.load_default()
    tw = d.textlength(a.label, font=fb)
    d.text(((W - tw) / 2, img.height + 12), a.label, font=fb, fill="#1F3864")
    tw2 = d.textlength(a.url, font=fr)
    d.text(((W - tw2) / 2, img.height + 50), a.url, font=fr, fill="#6B7688")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.save(p)
    print(f"-> {p}  ({out.width}x{out.height})")


if __name__ == "__main__":
    main()
