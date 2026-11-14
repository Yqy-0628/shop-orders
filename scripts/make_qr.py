# -*- coding: utf-8 -*-
"""给演示地址生成二维码。

用法：
    python scripts/make_qr.py --url http://10.64.126.63:8501 --no-url
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
    ap.add_argument("--no-url", action="store_true", help="不在图里印网址")
    a = ap.parse_args()

    qr = qrcode.QRCode(version=None, box_size=12, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(a.url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1F3864", back_color="white").convert("RGB")

    try:
        fb = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 30)
        fr = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
    except OSError:
        fb = fr = ImageFont.load_default()

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w_label = probe.textlength(a.label, font=fb)
    w_url = 0 if a.no_url else probe.textlength(a.url, font=fr)

    extra = 92 if not a.no_url else 64
    W = int(max(img.width, w_label + 32, w_url + 32))
    out = Image.new("RGB", (W, img.height + extra), "white")
    out.paste(img, ((W - img.width) // 2, 0))
    d = ImageDraw.Draw(out)

    d.text(((W - w_label) / 2, img.height + 16), a.label, font=fb, fill="#1F3864")

    if not a.no_url:
        d.text(((W - w_url) / 2, img.height + 58), a.url, font=fr, fill="#6B7688")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    out.save(p)
    print(f"-> {p}  ({out.width}x{out.height})")


if __name__ == "__main__":
    main()
