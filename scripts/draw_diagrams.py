# -*- coding: utf-8 -*-
"""画三张图：IPO / ER / 业务流程图。输出到 docs/。"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
OUT.mkdir(exist_ok=True)

NAVY = (31, 56, 100)
BLUE = (46, 84, 150)
LIGHT = (232, 240, 250)
GREY = (110, 118, 128)
LINE = (150, 160, 175)
WHITE = (255, 255, 255)
ACCENT = (176, 58, 58)
GOLD = (140, 96, 30)

FB = "C:/Windows/Fonts/msyhbd.ttc"
FR = "C:/Windows/Fonts/msyh.ttc"


def f(p, s):
    return ImageFont.truetype(p, s)


def tw(d, s, ft):
    b = d.textbbox((0, 0), s, font=ft)
    return b[2] - b[0], b[3] - b[1]


def center(d, box, s, ft, fill):
    x0, y0, x1, y1 = box
    w, h = tw(d, s, ft)
    d.text(((x0 + x1 - w) / 2, (y0 + y1 - h) / 2 - 3), s, font=ft, fill=fill)


def box(d, xy, fill, outline, r=12, w=2):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=w)


def arrow(d, p1, p2, color=LINE, w=3, head=12, dash=False):
    if dash:
        total = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n = max(2, int(total // 12))
        for i in range(n):
            if i % 2:
                continue
            a = (p1[0] + (p2[0] - p1[0]) * i / n, p1[1] + (p2[1] - p1[1]) * i / n)
            b = (p1[0] + (p2[0] - p1[0]) * (i + 1) / n, p1[1] + (p2[1] - p1[1]) * (i + 1) / n)
            d.line([a, b], fill=color, width=w)
    else:
        d.line([p1, p2], fill=color, width=w)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for s in (0.45, -0.45):
        d.line([p2, (p2[0] - head * math.cos(ang - s), p2[1] - head * math.sin(ang - s))],
               fill=color, width=w)


# ---------------------------------------------------------------- IPO
def chip(d, right, y, s, fill, fg):
    """框右上角的页面小标签。right 是标签右边缘的 x。"""
    ft = f(FR, 13)
    w, h = tw(d, s, ft)
    d.rounded_rectangle((right - w - 20, y, right, y + 22), radius=8, fill=fill)
    d.text((right - w - 14, y + 3), s, font=ft, fill=fg)


def draw_ipo():
    W, H = 1680, 1220
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    d.text((70, 34), "IPO 模型：订货决策系统的八个页面", font=f(FB, 40), fill=NAVY)
    d.text((72, 90), "输入 → 处理 → 输出　三列是整体映射，不是逐行对应；框右上角标的是它落在哪一页",
           font=f(FR, 18), fill=GREY)

    CW, CH, GAP = 460, 112, 138
    TOP, HEAD = 160, 84

    cols = [
        dict(x=70, title="输入 INPUT", note="四个入口：收银、导入、收银台账、设置",
             fill=(236, 243, 250), edge=BLUE, chipbg=(219, 231, 247),
             items=[("结账流水", "扫码入单，或导入历史销售 CSV", "收银 · 导入"),
                    ("售罄标记", "哪一款、几点卖光（一键）", "收银页"),
                    ("到货与报损", "入库 / 在途 / 报损 / 盘点", "收银·台账"),
                    ("商品档案", "分类 / 自制或进货 / 进价售价 / 供货商", "导入 · 设置"),
                    ("打印记录", "每款上次打了多少枚，次日沿用", "标签页")]),
        dict(x=610, title="处理 PROCESS", note="每天重算：μ → Q* → 建议 → 明日实测 → 回到 μ",
             fill=(240, 247, 240), edge=(58, 118, 78), chipbg=(226, 240, 228),
             items=[("需求补齐", "卖光后的缺口 × 同期时段销量率，还原真实需求", "core/pipeline"),
                    ("基线 + 趋势", "同星期几均值 × 近期趋势 → μ（均值）", "core/pipeline"),
                    ("报童模型", "临界比 → z　　Q* = μ + z·σ", "core/order"),
                    ("分档与诊断", "数据就绪度三档 + 品类订货偏差", "core/readiness"),
                    ("日结判定", "账实不符 / 剩余偏多 / 提前售罄 + 次日清单", "core/close")]),
        dict(x=1150, title="输出 OUTPUT", note="五个界面：每一框都能在屏幕上点到",
             fill=(252, 244, 236), edge=GOLD, chipbg=(248, 232, 213),
             items=[("备货清单", "进货按供货商分组导出，自制出排产单", "今日页"),
                    ("建议订货量", "保守 / 正常 / 积极 + 报童最优量 Q*", "订货页"),
                    ("错在哪（复盘）", "按建议订会差多少：省多少、代价怎么换", "复盘页"),
                    ("经营看板", "卖了多少 vs 进了多少、品类偏差", "看板页"),
                    ("标签与条码", "打印标签 → 扫码收银 → 回到输入", "标签页")]),
    ]

    for c in cols:
        x, y = c["x"], TOP
        box(d, (x, y, x + CW, y + HEAD), c["edge"], c["edge"], r=10)
        center(d, (x, y + 8, x + CW, y + 52), c["title"], f(FB, 24), WHITE)
        center(d, (x, y + 52, x + CW, y + 78), c["note"], f(FR, 13), WHITE)
        for j, (t, sub, page) in enumerate(c["items"]):
            by = TOP + HEAD + 16 + j * GAP
            box(d, (x, by, x + CW, by + CH), c["fill"], c["edge"])
            d.text((x + 20, by + 14), t, font=f(FB, 21), fill=NAVY)
            d.text((x + 20, by + 54), sub, font=f(FR, 15), fill=GREY)
            chip(d, x + CW - 12, by + CH - 30, page, c["chipbg"], GREY)

    # 两条大箭头：表达“整列流向整列”，而不是逐行对应
    ay = 560
    for x in (534, 1074):
        d.line([(x, ay), (x + 52, ay)], fill=BLUE, width=6)
        d.polygon([(x + 52, ay - 15), (x + 72, ay), (x + 52, ay + 15)], fill=BLUE)

    # 反馈回边：决策留痕与实际销量回灌成样本
    bottom = TOP + HEAD + 16 + 5 * GAP + CH
    ry = bottom + 70
    d.line([(1150 + CW / 2, bottom), (1150 + CW / 2, ry)], fill=(58, 118, 78), width=4)
    d.line([(1150 + CW / 2, ry), (300, ry)], fill=(58, 118, 78), width=4)
    d.line([(300, ry), (300, bottom + 4)], fill=(58, 118, 78), width=4)
    d.polygon([(285, bottom + 26), (300, bottom + 2), (315, bottom + 26)], fill=(58, 118, 78))
    center(d, (352, ry - 46, 1010, ry - 16),
           "反馈回边：谁下的单、建议多少、实际订多少、当天卖了多少 —— 全部回灌成下一天的样本",
           f(FB, 16), (58, 118, 78))

    d.text((70, H - 74), "读法：框内是本系统真的有的一步，不是设想的模块。政策/门店差异只改「商品档案」，"
                         "其余四层不动。", font=f(FR, 15), fill=GREY)
    d.text((70, H - 46), "三档：数据不足 14 天只做记录与补齐；14 天进过渡档；28 天才打开区间与报童建议。",
           font=f(FR, 15), fill=GREY)

    img.save(OUT / "ipo.png")
    print("ipo.png")


# ---------------------------------------------------------------- ER
def draw_er():
    W, H = 1700, 1050
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    d.text((70, 36), "数据模型：七张表", font=f(FB, 40), fill=NAVY)
    d.text((72, 92), "库存是派生量，事实是每一次增减；不单独建库存表",
           font=f(FR, 19), fill=GREY)

    fh, fb, fk = f(FB, 22), f(FR, 17), f(FB, 16)

    tables = {
        "sales": (70, 150, 430, [("id", "PK"), ("sku_id", "FK"), ("day 日期", ""),
                                 ("hour 时段", ""), ("weekday 星期", ""),
                                 ("qty 数量", ""), ("unit_price 售价", "")]),
        "stockout_mark": (70, 460, 430, [("id", "PK"), ("sku_id", "FK"), ("day 日期", ""),
                                         ("start_hour 起", ""), ("end_hour 止", "")]),
        "stock_move": (70, 720, 430, [("id", "PK"), ("sku_id", "FK"), ("day 日期", ""),
                                      ("type 入库/报损/盘点", ""), ("qty 数量（±）", ""),
                                      ("unit_cost 进价", ""), ("status 在途/已到货", "")]),
        "sku": (660, 150, 430, [("sku_id", "PK"), ("barcode 条码", "U"), ("name 品名", ""),
                                ("category 品类", ""), ("spec 规格", ""),
                                ("source 自制/进货", ""), ("supplier 供货商", ""),
                                ("cost 进价", ""), ("price 售价", ""),
                                ("salvage 残值", ""), ("shelf_life 保质期", ""),
                                ("mu / sigma 均值方差", "")]),
        "decision_log": (660, 590, 430, [("id", "PK"), ("ts 时间", ""),
                                         ("username 操作人", "FK"), ("sku_id", "FK"),
                                         ("params_json 参数", ""), ("q_star 建议量", ""),
                                         ("adopted_qty 实际订", ""), ("adopted 采纳", "")]),
        "app_user": (1210, 150, 380, [("username", "PK"), ("pwd_hash 密码哈希", ""),
                                      ("role 角色", "")]),
        "label_print": (1210, 380, 380, [("id", "PK"), ("day 日期", ""),
                                         ("sku_id", "FK"), ("qty 打印量", "")]),
    }

    geo = {}
    for name, (x, y, w, fields) in tables.items():
        h = 74 + 25 * len(fields) + 14
        geo[name] = (x, y, w, h)
        accent = ACCENT if name == "stockout_mark" else BLUE
        box(d, (x, y, x + w, y + 52), accent, accent, r=10)
        d.text((x + 18, y + 11), name, font=fh, fill=WHITE)
        if name == "stockout_mark":
            d.text((x + w - 126, y + 16), "★ 灵魂表", font=f(FB, 16), fill=WHITE)
        box(d, (x, y + 52, x + w, y + h), LIGHT, accent)
        for i, (nm, kind) in enumerate(fields):
            yy = y + 66 + i * 25
            d.text((x + 18, yy), nm, font=fb, fill=(40, 45, 55))
            if kind:
                d.text((x + w - 76, yy), kind, font=fk,
                       fill=ACCENT if kind == "PK" else GREY)

    sx, sy, sw, sh = geo["sku"]

    def fan(target, ty):
        tx, ty2, tww, th2 = geo[target]
        p1 = (sx, sy + ty)
        p2 = (tx + tww, ty2 + th2 / 2)
        arrow(d, p1, p2, color=LINE, w=3, head=10)
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        d.ellipse((mx - 5, my - 5, mx + 5, my + 5), fill=BLUE)
        d.text((mx + 10, my - 25), "1 : N", font=f(FB, 16), fill=BLUE)

    fan("sales", 100)
    fan("stockout_mark", 170)
    fan("stock_move", 240)

    dx, dy, dw, dh = geo["decision_log"]
    arrow(d, (sx + sw / 2, sy + sh), (dx + dw / 2, dy), color=LINE, w=3, head=10)
    d.text((sx + sw / 2 + 12, (sy + sh + dy) / 2 - 24), "1 : N", font=f(FB, 16), fill=BLUE)

    lx, ly, lw, lh = geo["label_print"]
    arrow(d, (sx + sw, sy + sh * 0.62), (lx, ly + lh / 2), color=LINE, w=3, head=10)
    d.text(((sx + sw + lx) / 2 - 4, sy + sh * 0.62 - 30), "1 : N", font=f(FB, 16), fill=BLUE)

    box(d, (1210, 610, 1590, 1030), (250, 251, 253), LINE)
    d.text((1230, 628), "设计要点", font=f(FB, 19), fill=NAVY)
    notes = ["· 外键全部指向 sku(sku_id)",
             "· 库存不落表，由流水实时重算",
             "· 报损记在 stock_move，qty 为负",
             "· 在途订单 status='在途'，不进库存",
             "· 决策留痕：谁、建议多少、实际订多少",
             "· sku.source 区分自制/进货，决定进哪张单",
             "· sku.supplier 让进货单按家分组，直接转发",
             "· label_print 记住每款上次打印量，次日沿用"]
    for i, s in enumerate(notes):
        d.text((1230, 664 + i * 30), s, font=f(FR, 16), fill=GREY)

    d.text((1230, 930), "售罄标记是灵魂表：", font=f(FB, 17), fill=ACCENT)
    d.text((1230, 958), "没有它，需求永远是残缺的。", font=f(FR, 16), fill=ACCENT)
    d.text((1230, 988), "两套真相 → 早晚对不上。", font=f(FR, 15), fill=GREY)

    img.save(OUT / "er.png")
    print("er.png")


# ---------------------------------------------------------------- 流程
def draw_flow():
    W, H = 1700, 920
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    d.text((60, 34), "业务流程：判断在开单之前，闭环在次日到货", font=f(FB, 38), fill=NAVY)
    d.text((62, 88), "灰色＝记录层（最小可用）　蓝色＝决策层（做深）　虚线＝旁路",
           font=f(FR, 18), fill=GREY)

    fh, fs = f(FB, 20), f(FR, 15)
    GREYF = (242, 243, 245)
    CW, CH = 300, 92

    def node(x, y, title, subs, fill, edge, dash=False):
        box(d, (x, y, x + CW, y + CH), fill, edge)
        d.text((x + 14, y + 10), title, font=fh, fill=NAVY)
        for i, s in enumerate(subs):
            d.text((x + 14, y + 40 + i * 21), s, font=fs, fill=GREY)

    node(60, 150, "① 建档与到货", ["商品档案 → 分类/来源/价格", "到货量、进价入账"], GREYF, GREY)
    node(420, 150, "② 顾客要买", ["扫一件标签码"], GREYF, GREY)
    node(780, 150, "③ 还有货吗？", ["库存 > 0"], WHITE, BLUE)
    node(1140, 150, "④ 开单扣库存", ["按档案价成交，记销售"], GREYF, GREY)

    node(60, 380, "⑨ 报损登记", ["过期 / 损坏"], GREYF, GREY, dash=True)
    node(420, 380, "⑥ 需求补齐", ["缺货时长 × 同期时段率"], LIGHT, BLUE)
    node(780, 380, "⑤ 售罄标记", ["一次点击，记时刻"], (252, 240, 240), ACCENT)
    node(1140, 380, "⑩ 经营看板", ["卖 vs 进 / 品类偏差"], (250, 250, 246), GOLD, dash=True)

    node(780, 600, "⑦ 订货决策", ["报童公式 → Q*"], LIGHT, BLUE)
    node(1140, 600, "⑧ 订货单", ["次日到货"], LIGHT, BLUE)

    arrow(d, (366, 196), (414, 196))
    arrow(d, (726, 196), (774, 196))
    arrow(d, (1086, 196), (1134, 196), color=BLUE)
    d.text((1090, 168), "是", font=f(FB, 17), fill=BLUE)

    arrow(d, (930, 248), (930, 374), color=ACCENT)
    d.text((946, 296), "否", font=f(FB, 17), fill=ACCENT)

    arrow(d, (776, 426), (724, 426), color=ACCENT)
    d.line([(570, 472), (570, 646)], fill=LINE, width=3)
    arrow(d, (570, 646), (774, 646))
    arrow(d, (1086, 646), (1134, 646))

    # 报损 → 冲减库存
    arrow(d, (210, 376), (210, 248), color=GREY, w=2, head=9, dash=True)
    d.text((222, 300), "冲减库存", font=f(FR, 14), fill=GREY)

    # 记录汇入看板
    arrow(d, (1084, 426), (1134, 426), color=GOLD, w=2, head=9, dash=True)
    d.text((1092, 398), "汇总", font=f(FR, 14), fill=GOLD)

    # 次日到货，回到 ①
    d.line([(1440, 646), (1580, 646), (1580, 130), (210, 130)], fill=LINE, width=3)
    arrow(d, (210, 130), (210, 146))
    d.text((1596, 640), "次日", font=f(FB, 16), fill=GREY)
    d.text((1596, 664), "到货", font=f(FR, 14), fill=GREY)

    # 核心主张放大成一条横带
    box(d, (60, 726, 1580, 816), (247, 249, 252), BLUE, r=10)
    d.text((84, 744), "整个项目只做一件事：", font=f(FB, 20), fill=NAVY)
    d.text((300, 742), "销量只记录成交，卖光的那几小时是空白；把空白补上，需求才第一次看得见。",
           font=f(FR, 21), fill=NAVY)

    d.text((84, 838), "建档在导入页：一次建完全部商品（分类、自制还是进货、进价售价、供货商），"
                      "① 的到货口径与 ④ 的成交价都由它来。", font=f(FR, 15), fill=GREY)

    img.save(OUT / "flow.png")
    print("flow.png")


if __name__ == "__main__":
    draw_ipo()
    draw_er()
    draw_flow()
    print(f"-> {OUT}")
