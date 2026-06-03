#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Имом Нававий «Қирқ ҳадис» — PDF генератор.

Маълумотни `index.html` дан ўқийди (QD массиви + муқаддима матни) ва сайтдаги
форматлашни (сарлавҳа, "N-ҳадис" рақами, "Ривояти:"/"Манба:") айнан такрорлаб
чиройли терилган PDF яратади.

Режимлар:
  python3 build_pdf.py            — ҳаммаси (тўлиқ + ҳар ҳадис алоҳида)
  python3 build_pdf.py --full     — фақат тўлиқ битта файл  (pdf/qirq-hadis.pdf)
  python3 build_pdf.py --hadis    — ҳар ҳадис алоҳида файл  (pdf/hadis-NN.pdf)

Кутубхона:  pip install fpdf2 uharfbuzz
Шрифт:      Inter (UI, кирилл) + Amiri (арабча, RTL) — fonts/ ичида commit қилинган.
"""

import argparse
import html as _html
import json
import os
import re
import sys

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except ImportError:
    sys.exit("fpdf2 топилмади. Ўрнатинг:  pip install fpdf2 uharfbuzz\n"
             "(агар _cffi_backend хатоси чиқса:  pip install --upgrade cffi)")

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "index.html")
FONT_DIR = os.path.join(ROOT, "fonts")
OUT_DIR = os.path.join(ROOT, "pdf")

# ── Палитра (босма учун — оч фон, тўқ матн, олтин акцент) ──────────────────
CREAM = (245, 240, 232)   # фон  (#f5f0e8 — сайтнинг light темаси)
TEXT = (42, 34, 24)       # асосий матн (#2a2218)
GOLD = (139, 105, 20)     # сарлавҳа/рақам (#8b6914)
GOLD_HI = (122, 92, 17)   # бир оз тўқроқ олтин (чизиқ)
DIM = (120, 113, 96)      # header/footer кулранг
QUOTE = (90, 80, 64)      # цитата матни (#5a5040)

# — Муқова (намунага мос: оқ фон, ўчроқ яшил сарлавҳа, минимал) —
COVER_GREEN = (78, 107, 79)   # сарлавҳа (ўчроқ яшил, намунадаги ранг)
COVER_DARK = (51, 51, 51)     # муаллиф/субтитр (қора-кулранг)
COVER_GRAY = (140, 140, 140)  # URL ва ажратувчи чизиқ

BOOK_TITLE = "«Қирқ ҳадис»"
BOOK_AUTHOR = "Имом Нававий"
BOOK_SITE = "https://abuyahyo.github.io/qirq-hadis/"
RUN_HEADER = "Имом Нававий — Қирқ ҳадис"


# ── Маълумотни index.html дан ўқиш ─────────────────────────────────────────
def load_data():
    src = open(SRC, encoding="utf-8").read()

    m = re.search(r"const QD=(\[.*?\n\]);", src, re.S)
    if not m:
        sys.exit("index.html ичидан QD массиви топилмади.")
    hadiths = json.loads(m.group(1))

    # Муқаддима — muq-body ичидаги <p> ва muq-quote блоклари (тартиб сақланади).
    i = src.index('<div class="muq-body">')
    j = src.index('<div id="searchPage">')
    body = src[i:j]
    muqaddima = []
    pat = re.compile(r'<p([^>]*)>(.*?)</p>|<div class="muq-quote">(.*?)</div>', re.S)
    for mm in pat.finditer(body):
        if mm.group(2) is not None:
            attrs, raw = mm.group(1), mm.group(2)
            kind = "closing" if "center" in attrs else "p"
        else:
            raw, kind = mm.group(3), "quote"
        txt = re.sub(r"<[^>]+>", "", raw)              # ички <span> ларни олиб ташлаш
        txt = _html.unescape(re.sub(r"\s+", " ", txt)).strip()
        if txt:
            muqaddima.append((kind, txt))
    return hadiths, muqaddima


# ── PDF класси ─────────────────────────────────────────────────────────────
class Book(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A5")
        self.set_margins(16, 20, 16)
        self.set_auto_page_break(True, margin=18)
        self.section_title = RUN_HEADER
        self.on_cover = False
        self.cover_pages = set()   # footer deferred — qaysi saҳifa muqova ekanini белгилаймиз
        self._register_fonts()
        self.set_fallback_fonts(["amiri"])

    def _register_fonts(self):
        idir = os.path.join(FONT_DIR, "Inter")
        adir = os.path.join(FONT_DIR, "Amiri")
        self.add_font("inter", "", os.path.join(idir, "Inter-Regular.ttf"))
        self.add_font("inter", "B", os.path.join(idir, "Inter-Bold.ttf"))
        self.add_font("inter", "I", os.path.join(idir, "Inter-Italic.ttf"))
        self.add_font("inter", "BI", os.path.join(idir, "Inter-BoldItalic.ttf"))
        self.add_font("amiri", "", os.path.join(adir, "Amiri-Regular.ttf"))

    # — фон + running header (матн тепада, чизиқ матн ОСТИДА) —
    def header(self):
        # Авто саҳифа-узилиши арабча (RTL shaping) блок ўртасида ишга тушса,
        # header матнидаги "1-" каби рақамлар бидиректция билан жойини алмашмаслиги
        # учун shaping'ни вақтинча ўчирамиз.
        saved = self.text_shaping
        self.text_shaping = None
        try:
            self._draw_header()
        finally:
            self.text_shaping = saved

    def _draw_header(self):
        if self.on_cover:
            # муқова — намунадагидек оқ фон, running header йўқ
            self.set_fill_color(255, 255, 255)
            self.rect(0, 0, self.w, self.h, style="F")
            self.set_y(self.t_margin)
            return
        # қолган саҳифаларга оч-крем фон
        self.set_fill_color(*CREAM)
        self.rect(0, 0, self.w, self.h, style="F")
        self.set_y(10)
        self.set_font("inter", "", 8.5)
        self.set_text_color(*DIM)
        # катакни ёзиб, y ни кейинги қаторга сурамиз — шунда чизиқ матнни кесмайди
        self.cell(0, 5, self.section_title, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        ly = self.get_y() + 1
        self.set_draw_color(*GOLD_HI)
        self.set_line_width(0.3)
        self.line(self.l_margin, ly, self.w - self.r_margin, ly)
        self.set_y(self.t_margin)

    def footer(self):
        saved = self.text_shaping
        self.text_shaping = None
        try:
            self._draw_footer()
        finally:
            self.text_shaping = saved

    def _draw_footer(self):
        is_cover = self.page in self.cover_pages
        self.set_y(-14)
        self.set_font("inter", "I" if is_cover else "", 9 if is_cover else 8.5)
        self.set_text_color(*(COVER_GRAY if is_cover else DIM))
        label = str(self.page_no()) if is_cover else f"— {self.page_no()} —"
        self.cell(0, 6, label, align="C")

    # — ёрдамчилар —
    def _uz(self, text, size=13, h=6.6, style="", color=TEXT, align="J", indent=0):
        self.set_font("inter", style, size)
        self.set_text_color(*color)
        if indent:
            self.set_x(self.l_margin + indent)
            w = self.w - self.l_margin - self.r_margin - 2 * indent
        else:
            w = 0
        self.multi_cell(w, h, text, align=align,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def _arabic(self, text, size=17, h=10):
        self.set_font("amiri", "", size)
        self.set_text_color(*TEXT)
        # Shaping'ни ФАҚАТ шу блок учун ёқамиз (глобал ёқилса файл шишиб кетади).
        self.set_text_shaping(use_shaping_engine=True, direction="rtl")
        self.multi_cell(0, h, text, align="R",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_shaping(use_shaping_engine=False)

    def _label_value(self, label, value):
        # "Ривояти: …" / "Манба: …" — label қалин, қиймат оддий, бир параграфда.
        self.set_text_color(*TEXT)
        self.set_font("inter", "B", 11.5)
        lw = self.get_string_width(label + " ")
        self.cell(lw, 6.2, label)
        self.set_font("inter", "", 11.5)
        self.multi_cell(0, 6.2, " " + value, align="L",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Бўлимлар ──
    def add_cover(self):
        # Намунага мос минимал муқова: оқ фон, катта яшил сарлавҳа, italic
        # муаллиф, қисқа ажратувчи чизиқ, иккита марказий қатор, пастда сайт URL.
        self.on_cover = True
        self.add_page()
        self.cover_pages.add(self.page)
        self.set_y(self.h * 0.28)
        # Сарлавҳа
        self.set_text_color(*COVER_GREEN)
        self.set_font("inter", "B", 33)
        self.multi_cell(0, 15, BOOK_TITLE, align="C",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        # Муаллиф (italic)
        self.set_text_color(*COVER_DARK)
        self.set_font("inter", "I", 16)
        self.cell(0, 9, BOOK_AUTHOR, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(9)
        # Қисқа марказий ажратувчи чизиқ
        cx = self.w / 2
        self.set_draw_color(*COVER_GRAY)
        self.set_line_width(0.4)
        self.line(cx - 32, self.get_y(), cx + 32, self.get_y())
        self.ln(13)
        # Иккита марказий қатор
        self.set_text_color(*COVER_DARK)
        self.set_font("inter", "", 14)
        self.cell(0, 9, "Ўзбекча ва арабча", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        self.cell(0, 9, "Тўлиқ тўплам — 42 ҳадис", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # Пастроқда сайт URL (italic, кулранг)
        self.set_y(self.h * 0.72)
        self.set_text_color(*COVER_GRAY)
        self.set_font("inter", "I", 12)
        self.cell(0, 8, BOOK_SITE, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.on_cover = False

    def add_muqaddima(self, blocks):
        self.section_title = "Имом Нававийнинг муқаддимаси"
        self.add_page()
        self.ln(4)
        self.set_text_color(*GOLD)
        self.set_font("inter", "B", 19)
        self.multi_cell(0, 9, "Имом Нававийнинг муқаддимаси", align="C",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)
        for kind, txt in blocks:
            if kind == "quote":
                self.ln(1)
                self._uz(txt, size=12.5, h=6.4, style="I", color=QUOTE,
                         align="J", indent=8)
                self.ln(1)
            elif kind == "closing":
                self.ln(3)
                self._uz(txt, size=12.5, h=6.4, style="I", color=GOLD_HI,
                         align="C")
            else:
                self._uz(txt, size=13, h=6.6)
            self.ln(2)

    def add_hadis(self, h):
        self.section_title = f"{h['id']}-ҳадис — {h['title']}"
        self.add_page()
        self.ln(2)
        # "N-ҲАДИС" (сайтда CSS uppercase — биз ҳам катта ҳарфда)
        self.set_text_color(*GOLD)
        self.set_font("inter", "B", 13)
        self.cell(0, 8, f"{h['id']}-ҲАДИС", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)
        # Сарлавҳа
        self.set_font("inter", "B", 16)
        self.multi_cell(0, 8, h["title"], align="C",
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)
        # Ўзбекча матн (\n → янги қатор/диалог)
        for para in h["text"].split("\n"):
            self._uz(para.strip(), size=13, h=6.8)
        # Арабча матн
        if h.get("arabic"):
            self.ln(4)
            self.set_draw_color(*GOLD_HI)
            self.set_line_width(0.2)
            y = self.get_y()
            self.line(self.l_margin, y, self.w - self.r_margin, y)
            self.ln(4)
            self._arabic(h["arabic"])
        self.ln(4)
        self._label_value("Ривояти:", h["narrator"])
        self.ln(1)
        self._label_value("Манба:", h["source"])


# ── Қурувчилар ─────────────────────────────────────────────────────────────
def build_full(hadiths, muqaddima, sample_ids=None):
    pdf = Book()
    pdf.set_title(BOOK_TITLE)
    pdf.set_author("Имом Нававий")
    pdf.add_cover()
    pdf.add_muqaddima(muqaddima)
    for h in hadiths:
        if sample_ids and h["id"] not in sample_ids:
            continue
        pdf.add_hadis(h)
    name = "qirq-hadis-namuna.pdf" if sample_ids else "qirq-hadis.pdf"
    out = os.path.join(OUT_DIR, name)
    pdf.output(out)
    return out


def build_per_hadis(hadiths):
    outs = []
    for h in hadiths:
        pdf = Book()
        pdf.set_title(f"{h['id']}-ҳадис: {h['title']}")
        pdf.set_author("Имом Нававий")
        pdf.add_hadis(h)
        out = os.path.join(OUT_DIR, f"hadis-{h['id']:02d}.pdf")
        pdf.output(out)
        outs.append(out)
    return outs


def main():
    ap = argparse.ArgumentParser(description="«Қирқ ҳадис» PDF генератор")
    ap.add_argument("--full", action="store_true", help="фақат тўлиқ битта файл")
    ap.add_argument("--hadis", action="store_true", help="ҳар ҳадис алоҳида файл")
    ap.add_argument("--sample", action="store_true",
                    help="намуна: муқаддима + 1–2-ҳадис (тасдиқ учун)")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    hadiths, muqaddima = load_data()
    do_all = not (args.full or args.hadis or args.sample)

    if args.sample:
        out = build_full(hadiths, muqaddima, sample_ids={1, 2})
        print(f"✓ Намуна:  {out}  ({os.path.getsize(out)//1024} KB)")
        return

    if args.full or do_all:
        out = build_full(hadiths, muqaddima)
        print(f"✓ Тўлиқ:   {out}  ({os.path.getsize(out)//1024} KB)")
    if args.hadis or do_all:
        outs = build_per_hadis(hadiths)
        total = sum(os.path.getsize(o) for o in outs)
        print(f"✓ Алоҳида: {len(outs)} файл (pdf/hadis-NN.pdf)  "
              f"жами {total//1024} KB")


if __name__ == "__main__":
    main()
