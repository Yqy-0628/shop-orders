# -*- coding: utf-8 -*-
"""把商品打成一张可打印的不干胶标签纸：品名、售价、到期日、Code128 条码。

尺寸按毫米给，内部按 dpi 换算像素，保证打印出来是真实尺寸。
纸张规格按常见不干胶排版给出，换纸只改预设，不动版式比例。
"""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from barcode import Code128
from barcode.writer import ImageWriter

FONT_PATH = Path(r"C:\Windows\Fonts\simhei.ttf")
FONT_FALLBACK = Path(r"C:\Windows\Fonts\msyh.ttc")

FONT_OK = FONT_PATH.exists() or FONT_FALLBACK.exists()

# 纸张预设：page 是成品幅面（毫米），cols/rows 是一页几枚，cell 是单枚尺寸。
PAPERS = {
    "A4 三列八行 · 62×34 毫米": dict(page=(210, 297), cols=3, rows=8,
                                    cell_w=62, cell_h=34),
    "A4 三列七行 · 65×38 毫米": dict(page=(210, 297), cols=3, rows=7,
                                    cell_w=65, cell_h=38),
    "A4 两列七行 · 99×38 毫米": dict(page=(210, 297), cols=2, rows=7,
                                    cell_w=99, cell_h=38),
    "卷纸 · 40×30 毫米（单枚）": dict(page=(40, 30), cols=1, rows=1,
                                     cell_w=40, cell_h=30),
    "卷纸 · 50×30 毫米（单枚）": dict(page=(50, 30), cols=1, rows=1,
                                     cell_w=50, cell_h=30),
}
DEFAULT_PAPER = "A4 三列八行 · 62×34 毫米"


def paper(name: str | None = None) -> dict:
    return PAPERS.get(name or DEFAULT_PAPER, PAPERS[DEFAULT_PAPER])


def per_page(name: str | None = None) -> int:
    p = paper(name)
    return p["cols"] * p["rows"]


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


def _draw_page(items, cfg, dpi):
    page_w_mm, page_h_mm = cfg["page"]
    cols, rows = cfg["cols"], cfg["rows"]
    cell_w_mm, cell_h_mm = cfg["cell_w"], cfg["cell_h"]

    page = Image.new("RGB", (_mm(page_w_mm, dpi), _mm(page_h_mm, dpi)), "white")
    draw = ImageDraw.Draw(page)

    grid_w_mm = cols * cell_w_mm
    grid_h_mm = rows * cell_h_mm
    left_mm = (page_w_mm - grid_w_mm) / 2
    top_mm = (page_h_mm - grid_h_mm) / 2

    # 版式全部按单枚高度的比例给，换纸时字号与条码跟着缩，不会挤成一团
    pad = min(2.0, cell_w_mm * 0.05, cell_h_mm * 0.06)
    f_name = _font(_mm(cell_h_mm * 0.106, dpi))
    f_price = _font(_mm(cell_h_mm * 0.100, dpi))
    f_small = _font(_mm(cell_h_mm * 0.076, dpi))
    f_code = _font(_mm(cell_h_mm * 0.070, dpi))

    name_y = cell_h_mm * 0.047
    sub_y = cell_h_mm * 0.176
    bar_y = cell_h_mm * 0.282
    bar_h_mm = cell_h_mm * 0.368
    code_y = cell_h_mm * 0.682

    for index, item in enumerate(items):
        r, c = divmod(index, cols)
        x0 = _mm(left_mm + c * cell_w_mm, dpi)
        y0 = _mm(top_mm + r * cell_h_mm, dpi)
        w = _mm(cell_w_mm, dpi)
        h = _mm(cell_h_mm, dpi)

        draw.rectangle([x0, y0, x0 + w - 1, y0 + h - 1], outline=(200, 200, 200), width=1)

        p = _mm(pad, dpi)
        tx = x0 + p
        ty = y0 + _mm(name_y, dpi)
        draw.text((tx, ty), item["name"], font=f_name, fill=(0, 0, 0))

        price_text = "￥%.2f" % item["price"]
        pw = draw.textlength(price_text, font=f_price)
        draw.text((x0 + w - p - pw, ty + _mm(0.2, dpi)), price_text,
                  font=f_price, fill=(0, 0, 0))

        sub = "保质 %d 天　到期 %s" % (item["shelf"], item["expire"])
        draw.text((tx, y0 + _mm(sub_y, dpi)), sub, font=f_small, fill=(70, 70, 70))

        bar_w = w - 2 * p
        bar = _barcode_image(item["barcode"], bar_w, _mm(bar_h_mm, dpi))
        page.paste(bar, (tx, y0 + _mm(bar_y, dpi)))

        cw = draw.textlength(item["barcode"], font=f_code)
        draw.text((x0 + (w - cw) / 2, y0 + _mm(code_y, dpi)),
                  item["barcode"], font=f_code, fill=(40, 40, 40))

    return page


def build_pages(items, paper_name: str | None = None, dpi: int = 300):
    cfg = paper(paper_name)
    per = cfg["cols"] * cfg["rows"]
    return [_draw_page(items[i:i + per], cfg, dpi)
            for i in range(0, len(items), per)]


def to_png_bytes(items, paper_name: str | None = None, dpi: int = 200):
    pages = build_pages(items, paper_name, dpi)
    if not pages:
        return b""
    buf = io.BytesIO()
    pages[0].save(buf, format="PNG")
    return buf.getvalue()


def to_pdf_bytes(items, paper_name: str | None = None, dpi: int = 300):
    pages = build_pages(items, paper_name, dpi)
    if not pages:
        return b""
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True,
                  append_images=pages[1:], resolution=dpi)
    return buf.getvalue()
