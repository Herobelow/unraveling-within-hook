#!/usr/bin/env python3
"""The 30-Day Focus Blueprint — premium ebook generator (Canva-style design system)."""
import os, sys
from fpdf import FPDF
from fpdf.enums import XPos, YPos, MethodReturnValue
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(BASE, "assets", "fonts")
A = os.path.join(BASE, "assets")

W, H = 612, 792            # US Letter, points
MX = 62                    # side margin
CW = W - 2 * MX            # content width

# ---------- palette ----------
NAVY    = (11, 18, 32)
NAVY2   = (17, 26, 45)
NAVY3   = (24, 36, 60)
INK     = (24, 30, 44)
MUTED   = (98, 107, 124)
CREAM   = (250, 247, 240)
CREAM2  = (243, 238, 227)
GOLD    = (224, 158, 38)
GOLD_D  = (176, 121, 20)
GOLD_BG = (252, 244, 226)
LINE    = (222, 214, 199)
WHITE   = (255, 255, 255)
SOFT    = (203, 211, 226)   # soft blue-grey text on navy
GHOST   = (36, 49, 78)      # ghost numerals on navy

TRACK = 2.2

class Book(FPDF):
    def __init__(self):
        super().__init__(unit="pt", format=(W, H))
        self.set_auto_page_break(False)
        self.set_title("The 30-Day Focus Blueprint — Rebuild Focus, Discipline & Deep Work in 30 Days")
        self.set_author("A. J. Mercer")
        self.set_subject("productivity, focus, discipline, habits, procrastination, deep work, time management, digital minimalism")
        self.set_keywords("focus ebook, discipline book, productivity ebook pdf, how to focus better, stop procrastinating, deep work guide, habit building, time management, digital minimalism, ADHD productivity, 30-day challenge")
        self.set_creator("Focus Blueprint Press")
        for fam, styles in {
            "Space": {"": "space-grotesk-latin-400-normal.ttf", "B": "space-grotesk-latin-700-normal.ttf"},
            "Inter": {"": "inter-latin-400-normal.ttf", "B": "inter-latin-700-normal.ttf", "I": "inter-latin-400-italic.ttf"},
            "InterM": {"": "inter-latin-500-normal.ttf"},
            "InterSB": {"": "inter-latin-600-normal.ttf"},
            "InterXB": {"": "inter-latin-800-normal.ttf"},
            "Playfair": {"I": "playfair-display-latin-600-italic.ttf", "BI": "playfair-display-latin-700-italic.ttf"},
        }.items():
            for st, fn in styles.items():
                self.add_font(fam, st, os.path.join(F, fn))
        self.page_no = 0
        self.header_label = ""
        self.toc = {}

    @property
    def t_y(self):
        return self.y

    @t_y.setter
    def t_y(self, v):
        self.y = v

    # ---------- primitives ----------
    def bg(self, color):
        self.set_fill_color(*color)
        self.rect(0, 0, W, H, style="F")

    def tracked(self, x, y, text, size, font="Inter", style="B", color=INK, spacing=TRACK, align="L", box_w=None):
        self.set_font(font, style, size)
        self.set_text_color(*color)
        widths = [self.get_string_width(c) for c in text]
        total = sum(widths) + spacing * (len(text) - 1)
        if align == "C":
            x = x + (box_w - total) / 2 if box_w else x - total / 2
        elif align == "R" and box_w:
            x = x + box_w - total
        for c, cw in zip(text, widths):
            self.text(x, y, c)
            x += cw + spacing
        return total

    def pill(self, cx, y, text, size=8.5, fg=GOLD, bg=None, border=GOLD, pad_x=10, h=20, font="Inter", style="B", spacing=1.6):
        self.set_font(font, style, size)
        tw = self.get_string_width(text) + spacing * (len(text) - 1)
        w = tw + pad_x * 2
        x = cx - w / 2
        if bg:
            self.set_fill_color(*bg)
        self.set_draw_color(*border)
        self.set_line_width(0.9)
        self.rect(x, y, w, h, style="DF" if bg else "D", round_corners=True, corner_radius=h / 2)
        self.tracked(cx, y + h / 2 + size * 0.36, text, size, font, style, fg, spacing, align="C")
        return w

    def rule(self, x, y, w, color=GOLD, width=1.4, dash=None):
        self.set_draw_color(*color)
        self.set_line_width(width)
        if dash:
            self.set_dash_pattern(dash=dash[0], gap=dash[1])
        self.line(x, y, x + w, y)
        if dash:
            self.set_dash_pattern()

    def dot3(self, cx, y, color=GOLD):
        self.set_fill_color(*color)
        for i in range(3):
            self.ellipse(cx - 10 + i * 8, y, 3.2, 3.2, style="F")

    # ---------- page chrome ----------
    def chrome(self, label, day=None):
        self.header_label = label
        self.page_no += 1
        self.tracked(MX, 40, label.upper(), 7.2, "Inter", "B", MUTED, 1.8)
        if day:
            self.tracked(W - MX, 40, day.upper(), 7.2, "Inter", "B", GOLD_D, 1.8, align="R", box_w=0)
            self.tracked(W - MX - self.get_string_width(day.upper()) - 1.8 * len(day), 40, "", 7.2)
        self.rule(MX, 50, CW, LINE, 0.9)
        # footer
        pn = str(self.page_no)
        self.set_font("Inter", "B", 8)
        self.set_text_color(*MUTED)
        self.tracked(W / 2, H - 30, pn, 8, "Inter", "B", MUTED, 1.2, align="C")
        self.set_draw_color(*LINE)
        self.set_line_width(0.8)
        self.line(W / 2 - 20, H - 42, W / 2 - 8, H - 42)
        self.line(W / 2 + 8, H - 42, W / 2 + 20, H - 42)
        self.y = 74

    def content_page(self, label="", day=None, bg=CREAM):
        self.set_page_background(bg)
        self.add_page()
        if label:
            self.chrome(label, day)
        return self.t_y

    # ---------- flow helpers ----------
    def need(self, h):
        if self.t_y + h > H - 64:
            self.content_page(self.header_label)
            return True
        return False

    def para(self, text, w=CW, size=10.5, lh=16.5, font="Inter", style="", color=INK, align="J", x=None):
        self.set_font(font, style, size)
        self.set_text_color(*color)
        h = self.multi_cell(w, lh, text, align=align, markdown=True, dry_run=True, output=MethodReturnValue.HEIGHT)
        if self.t_y + h > H - 64:
            self.content_page(self.header_label)
        self.multi_cell(w, lh, text, align=align, markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)

    def h2(self, text):
        self.need(58)
        self.set_fill_color(*GOLD)
        y = self.t_y + 3
        self.rect(MX, y, 26, 3.4, style="F")
        self.set_font("Space", "B", 20)
        self.set_text_color(*INK)
        self.set_xy(MX, y + 8)
        self.multi_cell(CW, 24, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(8)

    def h3(self, text, color=GOLD_D):
        self.need(40)
        self.tracked(MX, self.t_y + 9, text.upper(), 9.5, "InterXB", "", color, 1.9)
        self.ln(16)

    def bullets(self, items, w=CW, gap=8.5, size=10.5, lh=15.5):
        for it in items:
            self.set_font("Inter", "", size)
            h = self.multi_cell(w - 22, lh, it, markdown=True, dry_run=True, output=MethodReturnValue.HEIGHT)
            if self.t_y + h > H - 64:
                self.content_page(self.header_label)
            y = self.t_y
            self.set_fill_color(*GOLD)
            self.ellipse(MX + 2, y + lh * 0.42, 4.6, 4.6, style="F")
            self.set_xy(MX + 22, y)
            self.set_text_color(*INK)
            self.multi_cell(w - 22, lh, it, align="L", markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(gap - 4)

    def checklist(self, items, w=CW):
        for it in items:
            self.set_font("InterM", "", 10.5)
            h = self.multi_cell(w - 26, lh if (lh := 16) else 16, it, markdown=True, dry_run=True, output=MethodReturnValue.HEIGHT)
            if self.t_y + h + 4 > H - 64:
                self.content_page(self.header_label)
            y = self.t_y
            self.set_draw_color(*GOLD_D)
            self.set_fill_color(*WHITE)
            self.set_line_width(1)
            self.rect(MX + 1, y + 2.5, 10.5, 10.5, style="DF", round_corners=True, corner_radius=2.5)
            self.set_xy(MX + 26, y)
            self.set_text_color(*INK)
            self.multi_cell(w - 26, 16, it, align="L", markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(7)

    def panel(self, label, text, bg=GOLD_BG, bar=GOLD, label_color=GOLD_D, text_color=INK, italic=False, lh=15, size=10):
        self.set_font("Inter", "", size)
        h = self.multi_cell(CW - 58, lh, text, dry_run=True, output=MethodReturnValue.HEIGHT)
        total = h + 34
        if self.t_y + total > H - 64:
            self.content_page(self.header_label)
        y = self.t_y
        self.set_fill_color(*bg)
        self.rect(MX, y, CW, total, style="F", round_corners=True, corner_radius=8)
        self.set_fill_color(*bar)
        self.rect(MX, y, 3.6, total, style="F")
        self.tracked(MX + 20, y + 20, label.upper(), 8, "InterXB", "", label_color, 2)
        self.set_xy(MX + 20, y + 26)
        self.set_text_color(*text_color)
        style = "I" if italic else ""
        self.set_font("Inter", style, size)
        self.multi_cell(CW - 58, lh, text, align="L", markdown=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.t_y = y + total + 12

    def script_box(self, text, title="SAY THIS — WORD FOR WORD"):
        self.set_font("Playfair", "I", 11.5)
        h = self.multi_cell(CW - 60, 17.5, text, dry_run=True, output=MethodReturnValue.HEIGHT)
        total = h + 52
        if self.t_y + total > H - 64:
            self.content_page(self.header_label)
        y = self.t_y
        self.set_fill_color(*WHITE)
        self.set_draw_color(*GOLD)
        self.set_line_width(1.1)
        self.rect(MX, y, CW, total, style="DF", round_corners=True, corner_radius=8)
        self.set_fill_color(*GOLD)
        self.set_font("InterXB", "", 6.8)
        tw = self.get_string_width(title) + 1.6 * (len(title) - 1)
        bw = min(tw + 26, CW - 48)
        self.rect(MX + 24, y - 6.5, bw, 13, style="F", round_corners=True, corner_radius=6.5)
        self.tracked(MX + 24 + bw / 2, y + 3.4, title, 6.8, "InterXB", "", NAVY, 1.6, align="C")
        self.set_xy(MX + 28, y + 22)
        self.set_text_color(*INK)
        self.set_font("Playfair", "I", 11.5)
        self.multi_cell(CW - 60, 17.5, text, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.t_y = y + total + 12

    def quote(self, text, attrib=None):
        self.need(90)
        self.ln(8)
        self.set_font("Playfair", "BI", 15)
        self.set_text_color(*NAVY)
        h = self.multi_cell(CW - 40, 22, text, align="C", dry_run=True, output=MethodReturnValue.HEIGHT)
        if self.t_y + h + 30 > H - 80:
            self.content_page(self.header_label)
        self.set_text_color(*GOLD)
        self.set_font("Playfair", "BI", 30)
        self.set_xy(0, self.t_y - 2)
        self.cell(CW, 24, "\u201C", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Playfair", "BI", 15)
        self.set_text_color(*NAVY)
        self.multi_cell(CW - 40, 22, text, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if attrib:
            self.ln(2)
            self.tracked(W / 2, self.t_y + 2, attrib.upper(), 8, "Inter", "B", MUTED, 1.8, align="C")
        self.ln(14)

    def stats(self, items):
        gap = 12
        bw = (CW - gap * (len(items) - 1)) / len(items)
        total = 86
        if self.t_y + total > H - 64:
            self.content_page(self.header_label)
        y = self.t_y
        for i, (num, lab) in enumerate(items):
            x = MX + i * (bw + gap)
            self.set_fill_color(*WHITE)
            self.set_draw_color(*LINE)
            self.set_line_width(0.9)
            self.rect(x, y, bw, total, style="DF", round_corners=True, corner_radius=8)
            self.set_font("Space", "B", 21)
            self.set_text_color(*GOLD_D)
            self.set_xy(x, y + 14)
            self.cell(bw, 24, num, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("InterM", "", 7.6)
            self.set_text_color(*MUTED)
            self.set_xy(x + 10, y + 42)
            self.multi_cell(bw - 20, 10.5, lab.upper(), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.t_y = y + total + 14

    def steps(self, items, start=1):
        for i, (head, body) in enumerate(items, start=start):
            self.set_font("Inter", "", 10)
            h = self.multi_cell(CW - 46, 15, body, dry_run=True, output=MethodReturnValue.HEIGHT)
            hh = h + 30
            if self.t_y + hh > H - 64:
                self.content_page(self.header_label)
            y = self.t_y
            self.set_fill_color(*NAVY)
            self.ellipse(MX, y + 2, 24, 24, style="F")
            self.set_font("Space", "B", 12)
            self.set_text_color(*GOLD)
            self.set_xy(MX, y + 7.5)
            self.cell(24, 14, str(i), align="C")
            self.set_xy(MX + 38, y + 1)
            self.set_font("InterXB", "", 11)
            self.set_text_color(*INK)
            self.cell(CW - 40, 13, head)
            self.set_xy(MX + 38, y + 16)
            self.set_font("Inter", "", 10)
            self.set_text_color(*(70, 79, 96))
            self.multi_cell(CW - 46, 15, body, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.t_y = y + hh + 10

    def render_blocks(self, blocks):
        for b in blocks:
            kind = b[0]
            if kind == "lede":
                self.para(b[1], size=11.5, lh=18.5, font="InterM", style="", color=(45, 54, 72), align="L")
            elif kind == "p":
                self.para(b[1])
            elif kind == "h2":
                self.h2(b[1])
            elif kind == "h3":
                self.h3(b[1])
            elif kind == "bullets":
                self.bullets(b[1])
            elif kind == "check":
                self.checklist(b[1])
            elif kind == "tip":
                self.panel(b[1] if len(b) > 1 else "TRY THIS TODAY", b[-1])
            elif kind == "note":
                self.panel(b[1] if len(b) > 1 else "FIELD NOTE", b[-1], bg=NAVY2, bar=GOLD, label_color=GOLD, text_color=SOFT)
            elif kind == "script":
                self.script_box(b[1], b[2] if len(b) > 2 else "SAY THIS — WORD FOR WORD")
            elif kind == "quote":
                self.quote(b[1], b[2] if len(b) > 2 else None)
            elif kind == "divider":
                self.need(30)
                self.ln(10)
                self.dot3(W / 2, self.t_y)
                self.ln(20)
            elif kind == "stats":
                self.stats(b[1])
            elif kind == "steps":
                self.steps(b[1])
            elif kind == "custom":
                b[1](self)
            elif kind == "pb":
                self.content_page(self.header_label)

    # ---------- special pages ----------
    def cover(self):
        img = os.path.join(A, "cover-page.png")
        self.set_page_background(NAVY)
        self.add_page()
        self.image(img, 0, 0, W, H)
        # frame
        self.set_draw_color(*GOLD)
        self.set_line_width(1.1)
        self.rect(16, 16, W - 32, H - 32)
        # top badge
        self.pill(W / 2, 58, "FOCUS  •  DISCIPLINE  •  MOMENTUM", size=8, fg=GOLD, border=(122, 96, 40), h=21)
        # title block
        y = 96
        self.set_font("Space", "B", 56)
        self.set_text_color(*WHITE)
        self.set_xy(0, y)
        self.cell(W, 58, "THE 30-DAY", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*GOLD)
        self.cell(W, 58, "FOCUS", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*WHITE)
        self.cell(W, 58, "BLUEPRINT", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # subtitle with translucent scrim
        sub = "Rebuild your focus, defeat procrastination, and finish what you start — in 30 days, even if you’ve failed before."
        self.set_font("Playfair", "I", 14.5)
        sh_ = self.multi_cell(W - 150, 20, sub, align="C", dry_run=True, output=MethodReturnValue.HEIGHT)
        with self.local_context(fill_opacity=0.62):
            self.set_fill_color(*NAVY)
            self.rect(58, y + 176, W - 116, sh_ + 18, style="F", round_corners=True, corner_radius=8)
        self.set_text_color(*(232, 228, 218))
        self.set_xy(70, y + 185)
        self.multi_cell(W - 140, 20, sub, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # feature strip with translucent scrim
        strip = "30-DAY ACTION PLAN     ·     TRACKER TEMPLATES     ·     FOCUS SCRIPTS"
        self.set_font("Inter", "B", 8.2)
        sw_ = self.get_string_width(strip) + 1.2 * (len(strip) - 1)
        y2 = y + 262
        with self.local_context(fill_opacity=0.62):
            self.set_fill_color(*NAVY)
            self.rect(W / 2 - sw_ / 2 - 16, y2 - 11, sw_ + 32, 25, style="F", round_corners=True, corner_radius=12.5)
        self.tracked(W / 2, y2 + 3, strip, 8.2, "Inter", "B", GOLD, 1.2, align="C")
        # author
        self.rule(W / 2 - 26, H - 118, 52, GOLD, 1.6)
        self.tracked(W / 2, H - 92, "A. J. MERCER", 13, "Space", "B", WHITE, 3.4, align="C")
        self.tracked(W / 2, H - 72, "AUTHOR OF THE RESET SERIES", 7, "Inter", "B", (150, 158, 174), 2, align="C")

    def title_page(self):
        self.set_page_background(NAVY)
        self.add_page()
        self.set_draw_color(*(52, 66, 98))
        self.set_line_width(1)
        self.rect(28, 28, W - 56, H - 56)
        self.pill(W / 2, 96, "A 30-DAY SYSTEM", size=8, fg=GOLD, border=(96, 82, 44), h=20)
        self.set_font("Space", "B", 34)
        self.set_text_color(*WHITE)
        self.set_xy(0, 150)
        self.cell(W, 40, "The 30-Day", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*GOLD)
        self.cell(W, 40, "Focus Blueprint", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Playfair", "I", 13)
        self.set_text_color(*(210, 206, 196))
        self.set_xy(90, 250)
        self.multi_cell(W - 180, 19, "Rebuild your focus, defeat procrastination, and finish what you start — even if you\u2019ve failed before.", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.dot3(W / 2, 330)
        self.tracked(W / 2, 372, "A. J. MERCER", 11, "Space", "B", WHITE, 3, align="C")
        self.tracked(W / 2, 560, "FOCUS BLUEPRINT PRESS", 7.5, "Inter", "B", (140, 149, 166), 2.4, align="C")
        self.tracked(W / 2, 578, "FIRST EDITION", 7.5, "Inter", "B", (140, 149, 166), 2.4, align="C")

    def copyright(self):
        self.set_page_background(CREAM)
        self.add_page()
        self.set_xy(MX, 100)
        self.set_font("Inter", "", 8.8)
        self.set_text_color(*(90, 98, 114))
        txt = ("The 30-Day Focus Blueprint — Rebuild Your Focus, Discipline & Deep Work in 30 Days\n\n"
               "Copyright \u00A9 2026 A. J. Mercer. All rights reserved.\n\n"
               "No part of this publication may be reproduced, distributed, or transmitted in any form or by any means, "
               "including photocopying, recording, or other electronic or mechanical methods, without the prior written "
               "permission of the publisher, except in the case of brief quotations embodied in reviews and certain other "
               "noncommercial uses permitted by copyright law.\n\n"
               "DISCLAIMER: This book is for informational and educational purposes only. It is not medical, psychological, "
               "or professional advice. If you suspect you have ADHD, anxiety, depression, or any other condition that affects "
               "your attention, please consult a qualified health professional. The author assumes no responsibility for errors, "
               "omissions, or outcomes resulting from the use of this information.\n\n"
               "Trademarks: All product names, logos, and brands mentioned are property of their respective owners.\n\n"
               "Cover and interior design: Focus Blueprint Press Studio\n"
               "Typefaces: Space Grotesk, Inter, Playfair Display\n\n"
               "First Edition — 2026\n"
               "focusblueprint.press")
        self.multi_cell(CW, 13.5, txt, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def toc_page(self, entries):
        self.set_page_background(NAVY)
        self.add_page()
        self.tracked(MX, 88, "CONTENTS", 12, "InterXB", "", GOLD, 4)
        self.rule(MX, 102, 44, GOLD, 2)
        y = 136
        for num, title, page, kind in entries:
            if kind == "part":
                y += 10
                self.tracked(MX, y + 8, title.upper(), 9.5, "InterXB", "", GOLD, 2.6)
                y += 26
                continue
            self.set_font("InterM", "", 11)
            self.set_text_color(*(226, 229, 238))
            self.set_xy(MX + (26 if num else 0), y)
            self.cell(CW - 60, 14, title)
            self.set_font("Space", "B", 10)
            self.set_text_color(*GOLD)
            self.set_xy(W - MX - 30, y)
            self.cell(30, 14, str(page), align="R")
            title_w = self.get_string_width(title) + (3.4 if num else 0)
            self.set_draw_color(*(48, 60, 88))
            self.set_line_width(0.7)
            self.set_dash_pattern(dash=1.2, gap=2.6)
            self.line(MX + (26 if num else 0) + title_w + 14, y + 10, W - MX - 42, y + 10)
            self.set_dash_pattern()
            y += 25
        self.t_y = y

    def part_page(self, roman, title, subtitle, num):
        self.set_page_background(NAVY)
        self.add_page()
        self.page_no += 1
        # ghost number
        self.set_font("Space", "B", 300)
        self.set_text_color(*GHOST)
        self.set_xy(0, 130)
        self.cell(W, 330, num, align="C")
        self.pill(W / 2, 200, roman.upper(), size=9, fg=GOLD, border=(110, 92, 46), h=22)
        self.set_font("Space", "B", 30)
        self.set_text_color(*WHITE)
        self.set_xy(40, 268)
        self.multi_cell(W - 80, 36, title, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Playfair", "I", 13)
        self.set_text_color(*(206, 202, 192))
        self.set_xy(110, 382)
        self.multi_cell(W - 220, 19, subtitle, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.rule(W / 2 - 24, 470, 48, GOLD, 1.6)
        self.tracked(W / 2, H - 40, str(self.page_no), 8, "Inter", "B", (120, 130, 148), 1.2, align="C")

    def chapter_opener(self, part_label, days, num, title, subtitle, bullets):
        self.set_page_background(NAVY)
        self.add_page()
        self.page_no += 1
        self.tracked(MX, 84, part_label.upper(), 8, "InterXB", "", GOLD, 2.4)
        self.tracked(W - MX, 84, days.upper(), 8, "InterXB", "", (130, 141, 160), 2, align="R", box_w=0)
        self.rule(MX, 96, CW, (52, 66, 98), 1)
        # ghost chapter number
        self.set_font("Space", "B", 150)
        self.set_text_color(*GHOST)
        self.set_xy(MX, 116)
        self.cell(160, 150, num)
        self.set_font("Space", "B", 27)
        self.set_text_color(*WHITE)
        self.set_xy(MX + 165, 152)
        self.multi_cell(CW - 165, 33, title, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Playfair", "I", 12.5)
        self.set_text_color(*(196, 202, 214))
        self.set_xy(MX + 165, self.t_y + 6)
        self.multi_cell(CW - 165, 18, subtitle, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # in this chapter
        y = 330
        self.set_fill_color(*NAVY2)
        self.rect(MX, y, CW, 232, style="F", round_corners=True, corner_radius=10)
        self.set_fill_color(*GOLD)
        self.rect(MX, y, 3.6, 232, style="F")
        self.tracked(MX + 24, y + 30, "IN THIS CHAPTER", 8.5, "InterXB", "", GOLD, 2.4)
        yy = y + 48
        for b in bullets:
            self.set_font("Inter", "", 10.5)
            self.set_text_color(*(214, 219, 230))
            h = self.multi_cell(CW - 66, 16, b, dry_run=True, output=MethodReturnValue.HEIGHT)
            self.set_fill_color(*GOLD)
            self.ellipse(MX + 26, yy + 5.5, 4.4, 4.4, style="F")
            self.set_xy(MX + 44, yy)
            self.multi_cell(CW - 66, 16, b, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            yy += h + 8
        self.tracked(W / 2, H - 40, str(self.page_no), 8, "Inter", "B", (120, 130, 148), 1.2, align="C")

    # ---------- workbook templates ----------
    def planner_page(self, label="THE DAILY FOCUS PLANNER"):
        self.content_page("TOOLKIT")
        self.h2(label)
        self.tracked(MX, self.t_y + 2, "PRINT ONE PER DAY  ·  FILL IT BEFORE YOU OPEN ANY APP", 7.5, "Inter", "B", MUTED, 1.8)
        self.ln(20)
        y = self.t_y
        def box(y, h, title, inner=None):
            self.set_fill_color(*WHITE)
            self.set_draw_color(*LINE)
            self.set_line_width(1)
            self.rect(MX, y, CW, h, style="DF", round_corners=True, corner_radius=7)
            self.set_fill_color(*GOLD_BG)
            self.rect(MX + 1.2, y + 1.2, CW - 2.4, 22, style="F")
            self.tracked(MX + 14, y + 15, title, 7.8, "InterXB", "", GOLD_D, 2)
            if inner:
                inner(y + 23.2, h - 24.4)
        def lines(n, x0, x1, y0, gap=20):
            self.set_draw_color(*(210, 203, 188))
            self.set_line_width(0.8)
            for i in range(n):
                self.line(x0, y0 + i * gap, x1, y0 + i * gap)
        box(y, 96, "TODAY  ·  DATE _________  ·  MY ONE NON-NEGOTIABLE")
        self.tracked(MX + 16, y + 52, "1.", 11, "Space", "B", GOLD_D, 1)
        lines(2, MX + 40, W - MX - 20, y + 62, 24)
        y2 = y + 96 + 12
        box(y2, 150, "TOP 3 PRIORITIES  —  WHAT ACTUALLY MOVES MY LIFE FORWARD?")
        for i in range(3):
            self.tracked(MX + 16, y2 + 52 + i * 32, f"{i+1}.", 11, "Space", "B", GOLD_D, 1)
        lines(3, MX + 40, W - MX - 20, y2 + 62, 32)
        y3 = y2 + 150 + 12
        box(y3, 118, "FOCUS BLOCKS  —  SHADE ONE CIRCLE PER COMPLETED 50-MINUTE BLOCK")
        self.set_draw_color(*GOLD_D)
        self.set_line_width(1)
        for r in range(2):
            for c in range(8):
                cx = MX + 26 + c * 52 + r * 26
                cy = y3 + 48 + r * 30
                self.ellipse(cx, cy, 18, 18)
        self.tracked(MX + 16, y3 + 108, "BLOCK 1: ____________     BLOCK 2: ____________     BLOCK 3: ____________", 7.8, "InterM", "", MUTED, 0.8)
        y4 = y3 + 118 + 12
        box(y4, 84, "TONIGHT  ·  THREE WINS  +  TOMORROW\u2019S FIRST MOVE")
        lines(2, MX + 16, W - MX - 16, y4 + 46, 22)

    def tracker_page(self, label="THE 30-DAY HABIT TRACKER"):
        self.content_page("TOOLKIT")
        self.h2(label)
        self.tracked(MX, self.t_y + 2, "SHADE A CIRCLE EVERY DAY YOU SHOW UP.  NEVER MISS TWICE.", 7.5, "Inter", "B", MUTED, 1.8)
        self.ln(20)
        y = self.t_y
        habits = ["Habit 1: ______________", "Habit 2: ______________", "Habit 3: ______________", "Habit 4: ______________"]
        rows = 4
        row_h = 100
        for r in range(rows):
            ry = y + r * row_h
            self.set_fill_color(*WHITE)
            self.set_draw_color(*LINE)
            self.set_line_width(1)
            self.rect(MX, ry, CW, row_h - 12, style="DF", round_corners=True, corner_radius=7)
            self.set_font("InterM", "", 9.5)
            self.set_text_color(*INK)
            self.set_xy(MX + 14, ry + 10)
            self.cell(200, 14, habits[r])
            self.set_draw_color(*GOLD_D)
            self.set_line_width(1)
            for d in range(30):
                cx = MX + 16 + (d % 15) * 32.6
                cy = ry + 34 + (d // 15) * 27
                self.ellipse(cx, cy, 16, 16)
                self.set_font("Inter", "", 6)
                self.set_text_color(*GOLD_D)
                self.set_xy(cx - 2, cy + 5)
                self.cell(20, 8, str(d + 1), align="C")
        y2 = y + rows * row_h + 8
        self.panel("THE NEVER-MISS-TWICE RULE", "Missing once is an accident. Missing twice is the start of a new (bad) habit. "
                   "If you break the chain today, your only job tomorrow is to show up for one tiny session — two minutes counts. The chain resumes; the identity stays intact.")

    def weekly_review_page(self):
        self.content_page("TOOLKIT")
        self.h2("THE WEEKLY REVIEW — 20 MINUTES, EVERY SUNDAY")
        self.tracked(MX, self.t_y + 2, "THE SINGLE MEETING THAT KEEPS THE WHOLE SYSTEM ALIVE", 7.5, "Inter", "B", MUTED, 1.8)
        self.ln(22)
        y = self.t_y
        qs = [
            ("1  ·  WHAT WORKED? (KEEP)", "Which block, habit, or environment tweak gave me the most focus per minute?"),
            ("2  ·  WHAT LEAKED? (FIX OR CUT)", "Where did attention actually go? Name the top 2 attention thieves of the week."),
            ("3  ·  WHAT\u2019S THE ONE THING NEXT WEEK?", "If next week produces only ONE result, what must it be? Which day and time is its first block?"),
            ("4  ·  MY WEEKLY EXPERIMENT", "One small change I will test for 7 days (earlier block, phone drawer, new stack, stricter shutdown)..."),
        ]
        yy = y
        for title, q in qs:
            h = 108
            self.set_fill_color(*WHITE)
            self.set_draw_color(*LINE)
            self.set_line_width(1)
            self.rect(MX, yy, CW, h, style="DF", round_corners=True, corner_radius=7)
            self.set_fill_color(*NAVY)
            self.rect(MX + 1.2, yy + 1.2, CW - 2.4, 22, style="F")
            self.tracked(MX + 14, yy + 15, title, 7.8, "InterXB", "", GOLD, 2)
            self.set_font("Inter", "I", 8.8)
            self.set_text_color(*MUTED)
            self.set_xy(MX + 14, yy + 28)
            self.multi_cell(CW - 28, 11, q, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_draw_color(*(214, 207, 192))
            self.set_line_width(0.8)
            for i in range(3):
                self.line(MX + 16, yy + 62 + i * 15, W - MX - 16, yy + 62 + i * 15)
            yy += h + 10

    def plan_page(self, part_rows, heading, intro=None):
        self.content_page("THE 30-DAY BLUEPRINT")
        self.h2(heading)
        if intro:
            self.para(intro, align="J")
        self.ln(0)
        col = [42, 118, CW - 42 - 118]
        y = self.t_y
        # header row
        self.set_fill_color(*NAVY)
        self.rect(MX, y, CW, 24, style="F", round_corners=True, corner_radius=5)
        self.tracked(MX + 14, y + 16, "DAY", 7.6, "InterXB", "", GOLD, 1.6)
        self.tracked(MX + col[0] + 14, y + 16, "FOCUS", 7.6, "InterXB", "", GOLD, 1.6)
        self.tracked(MX + col[0] + col[1] + 14, y + 16, "CORE ACTION — DO EXACTLY THIS", 7.6, "InterXB", "", GOLD, 1.6)
        y += 24
        for i, (day, focus, action) in enumerate(part_rows):
            self.set_font("Inter", "", 8.6)
            h_a = self.multi_cell(col[2] - 24, 11, action, dry_run=True, output=MethodReturnValue.HEIGHT)
            rh = max(21, h_a + 9)
            if y + rh > H - 60:
                self.content_page("THE 30-DAY BLUEPRINT")
                y = self.t_y + 6
                self.set_fill_color(*NAVY)
                self.rect(MX, y, CW, 24, style="F", round_corners=True, corner_radius=5)
                self.tracked(MX + col[0] + col[1] + 14, y + 16, "CORE ACTION — DO EXACTLY THIS", 7.6, "InterXB", "", GOLD, 1.6)
                y += 24
            if i % 2 == 0:
                self.set_fill_color(*(255, 252, 246))
                self.rect(MX, y, CW, rh, style="F")
            self.set_draw_color(*LINE)
            self.set_line_width(0.6)
            self.rect(MX, y, CW, rh)
            self.set_font("Space", "B", 9.5)
            self.set_text_color(*GOLD_D)
            self.set_xy(MX + 14, y + 5)
            self.cell(col[0] - 20, 12, day)
            self.set_font("InterSB", "", 8.6)
            self.set_text_color(*INK)
            self.set_xy(MX + col[0] + 12, y + 6)
            self.cell(col[1] - 20, 11, focus)
            self.set_font("Inter", "", 8.6)
            self.set_text_color(*(70, 78, 94))
            self.set_xy(MX + col[0] + col[1] + 12, y + 4.5)
            self.multi_cell(col[2] - 22, 11, action, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            y += rh
        self.t_y = y + 10

    def closing(self):
        self.set_page_background(NAVY)
        self.add_page()
        self.page_no += 1
        self.pill(W / 2, 150, "ONE LAST THING", size=8.5, fg=GOLD, border=(110, 92, 46), h=21)
        self.set_font("Space", "B", 26)
        self.set_text_color(*WHITE)
        self.set_xy(70, 200)
        self.multi_cell(W - 140, 33, "Discipline isn\u2019t a trait.\nIt\u2019s a system you now own.", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Playfair", "I", 12.5)
        self.set_text_color(*(204, 208, 218))
        self.set_xy(120, 300)
        self.multi_cell(W - 240, 19, "Thirty days from now, you won\u2019t be a different person. You\u2019ll be the same person with a different default: start, focus, finish, repeat.", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.dot3(W / 2, 380)
        self.tracked(W / 2, 430, "START TODAY. DAY 1 COUNTS THE MOMENT YOU CLOSE THIS BOOK.", 8.5, "InterXB", "", GOLD, 2, align="C")
        self.tracked(W / 2, H - 40, str(self.page_no), 8, "Inter", "B", (120, 130, 148), 1.2, align="C")

    def resources_page(self):
        self.content_page("RESOURCES")
        self.h2("YOUR NEXT STEPS")
        self.bullets([
            "**Print the toolkit** — the planner, tracker, and weekly review work best on paper, on your desk.",
            "**Pick your launch date** — circle it. Tell one person. Public commitment doubles follow-through.",
            "**Do Day 1 today** — one 25-minute block on your Most Important Task. That\u2019s the whole assignment.",
            "**Struggling?** Return to Chapter 6. Procrastination is a launch problem, not a character problem.",
            "**Suspect ADHD or anxiety?** This system helps — but pair it with professional support. That\u2019s strength, not weakness.",
        ])
        self.panel("FREE COMPANION KIT", "Get the printable planner pack, the digital tracker (Notion + spreadsheet), and bonus focus scripts at: focusblueprint.press/kit — free for readers of this book.")
        self.quote("You do not rise to the level of your goals. You fall to the level of your systems.", "JAMES CLEAR, ATOMIC HABITS")
        self.para("Thank you for trusting this book with thirty days of your life. If it helped you finish what you started, "
                   "an honest review helps the next distracted reader find it — and it takes ninety seconds. That\u2019s one-tenth of a focus block. You have time.")
        self.ln(6)
        self.tracked(0, self.t_y + 8, "— A. J. MERCER", 10, "Space", "B", INK, 2.4, align="C")
