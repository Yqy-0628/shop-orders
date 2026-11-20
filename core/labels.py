# -*- coding: utf-8 -*-
"""把商品打成一张可打印的不干胶标签纸：品名、售价、到期日、Code128 条码。

尺寸按毫米给，内部按 dpi 换算像素，保证打印出来是真实尺寸。
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from barcode import Code128
from barcode.writer import ImageWriter

FONT_PATH = Path(r"C:\Windows\Fonts\simhei.ttf")
FONT_FALLBACK = Path(r"C:\Windows\Fonts\msyh.ttc")

A4_MM = (210, 297)
FONT_OK = FONT_PATH.exists() or FONT_FALLBACK.exists()


def _font(size_px):
    path = FONT_PATH if FONT_PATH.exists() else FONT_FALLBACK
    try:
        return ImageFont.truetype(str(path), size_px)
    except Exception:
        return ImageFont.load_default()


def _mm(value, dpi):
    return int(round(value * dpi / 25.4))


def _barcode_image(code, width_px, height_px):
    img = Code128(code, writer=ImageWriter()).render({
        "module_width": 0.22,
        "module_height": 10,
        "quiet_zone": 1.0,
        "font_size": 0,
        "text_distance": 0,
    })
    img = img.convert("L")
    w, h = img.size
    scale = min(width_px / w, height_px / h)
    new = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new, Image.LANCZOS).convert("RGB")


def _draw_page(items, cols, rows, dpi):
    page = Image.new("RGB", (_mm(A4_MM[0], dpi), _mm(A4_MM[1], dpi)), "white")
    draw = ImageDraw.Draw(page)

    cell_w_mm = 62
    cell_h_mm = 34
    grid_w_mm = cols * cell_w_mm
    grid_h_mm = rows * cell_h_mm
    left_mm = (A4_MM[0] - grid_w_mm) / 2
    top_mm = (A4_MM[1] - grid_h_mm) / 2

    f_name = _font(_mm(3.6, dpi))
    f_price = _font(_mm(3.4, dpi))
    f_small = _font(_mm(2.6, dpi))
    f_code = _font(_mm(2.4, dpi))

    for index, item in enumerate(items):
        r, c = divmod(index, cols)
        x0 = _mm(left_mm + c * cell_w_mm, dpi)
        y0 = _mm(top_mm + r * cell_h_mm, dpi)
        w = _mm(cell_w_mm, dpi)
        h = _mm(cell_h_mm, dpi)

        draw.rectangle([x0, y0, x0 + w - 1, y0 + h - 1], outline=(200, 200, 200), width=1)

        pad = _mm(2.0, dpi)
        tx = x0 + pad
        ty = y0 + _mm(1.6, dpi)
        draw.text((tx, ty), item["name"], font=f_name, fill=(0, 0, 0))

        price_text = "￥%.2f" % item["price"]
        pw = draw.textlength(price_text, font=f_price)
        draw.text((x0 + w - pad - pw, ty + _mm(0.2, dpi)), price_text,
                  font=f_price, fill=(0, 0, 0))

        sub = "保质 %d 天　到期 %s" % (item["shelf"], item["expire"])
        draw.text((tx, y0 + _mm(6.0, dpi)), sub, font=f_small, fill=(70, 70, 70))

        bar_w = w - 2 * pad
        bar_h = _mm(12.5, dpi)
        bar = _barcode_image(item["barcode"], bar_w, bar_h)
        page.paste(bar, (tx, y0 + _mm(9.6, dpi)))

        cw = draw.textlength(item["barcode"], font=f_code)
        draw.text((x0 + (w - cw) / 2, y0 + _mm(23.2, dpi)),
                  item["barcode"], font=f_code, fill=(40, 40, 40))

    return page


def build_pages(items, cols=3, rows=8, dpi=300):
    per = cols * rows
    pages = []
    for i in range(0, len(items), per):
        pages.append(_draw_page(items[i:i + per], cols, rows, dpi))
    return pages


def to_png_bytes(items, cols=3, rows=8, dpi=200):
    pages = build_pages(items, cols, rows, dpi)
    if not pages:
        return b""
    buf = io.BytesIO()
    pages[0].save(buf, format="PNG")
    return buf.getvalue()


def to_pdf_bytes(items, cols=3, rows=8, dpi=300):
    pages = build_pages(items, cols, rows, dpi)
    if not pages:
        return b""
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True,
                  append_images=pages[1:], resolution=dpi)
    return buf.getvalue()
