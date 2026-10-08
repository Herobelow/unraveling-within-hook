#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebook import *
from content import WELCOME, PROBLEM, CHAPTERS, PLAN_WEEKS
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
A = os.path.join(BASE, "assets")
OUT_PDF = os.path.join(ROOT, "The-30-Day-Focus-Blueprint.pdf")

# ---------------- cover crop ----------------
src = Image.open(os.path.join(A, "cover-art.png")).convert("RGB")
sw, sh = src.size
crop_h = int(sw * H / W)                     # full width, height matched to page ratio
top = int((sh - crop_h) * 0.40)
img = src.crop((0, top, sw, top + crop_h)).resize((W * 2, H * 2), Image.LANCZOS)
# navy gradient overlays: text-safe zones top & bottom
ow, oh = img.size
overlay = Image.new("L", (1, oh), 0)
for y in range(oh):
    t = y / oh
    a = 0
    if t < 0.40: a = int(215 * (1 - t / 0.40) ** 1.1)
    if t > 0.72: a = max(a, int(225 * ((t - 0.72) / 0.28) ** 1.0))
    overlay.putpixel((0, y), a)
overlay = overlay.resize((ow, oh))
navy = Image.new("RGB", (ow, oh), NAVY)
img = Image.composite(navy, img, overlay)
img.save(os.path.join(A, "cover-page.png"))

# ---------------- OG image ----------------
def make_og():
    og = Image.new("RGB", (1200, 630), NAVY)
    art = src.resize((int(sh * 0.78), 1260), Image.LANCZOS)
    aw, ah = art.size
    art = art.crop((int(aw * 0.25), 300, aw, 300 + 630))
    og.paste(art, (1200 - art.size[0], 0))
    # left gradient blend
    grad = Image.new("L", (300, 630), 0)
    d = ImageDraw.Draw(grad)
    for x in range(300):
        d.line([(x, 0), (x, 630)], fill=int(255 * (1 - x / 300)))
    base = Image.new("RGB", (300, 630), NAVY)
    og.paste(base, (1200 - art.size[0] - 300 + 1, 0), grad)
    dr = ImageDraw.Draw(og)
    fd = os.path.join(A, "fonts")
    f_small = ImageFont.truetype(os.path.join(fd, "inter-latin-700-normal.ttf"), 21)
    f_big = ImageFont.truetype(os.path.join(fd, "space-grotesk-latin-700-normal.ttf"), 74)
    f_sub = ImageFont.truetype(os.path.join(fd, "playfair-display-latin-600-italic.ttf"), 27)
    f_au = ImageFont.truetype(os.path.join(fd, "space-grotesk-latin-700-normal.ttf"), 22)
    # tracking helper
    def tracked(x, y, s, font, fill, sp):
        for c in s:
            dr.text((x, y), c, font=font, fill=fill)
            x += dr.textlength(c, font=font) + sp
    tracked(90, 92, "F O C U S   ·   D I S C I P L I N E   ·   M O M E N T U M", f_small, (224, 158, 38), 0)
    dr.line([(92, 138), (560, 138)], fill=(224, 158, 38), width=3)
    tracked(86, 178, "THE 30-DAY", f_big, (255, 255, 255), 2)
    tracked(86, 272, "FOCUS", f_big, (224, 158, 38), 4)
    tracked(86, 366, "BLUEPRINT", f_big, (255, 255, 255), 2)
    for i, line in enumerate(["Rebuild your focus, defeat procrastination,",
                               "and finish what you start — in 30 days."]):
        dr.text((92, 480 + i * 38), line, font=f_sub, fill=(214, 210, 200))
    dr.text((92, 576), "A. J. MERCER", font=f_au, fill=(240, 240, 244))
    og.save(os.path.join(A, "og-image.png"))

make_og()

# ---------------- two-pass build ----------------
def render_book(toc_map=None):
    book = Book()
    # 1 cover
    book.cover(); book.page_no = 1
    # 2 title
    book.title_page(); book.page_no = 2
    # 3 copyright
    book.copyright(); book.page_no = 3
    # 4 toc
    entries = []
    if toc_map:
        entries.append(("", "How This 30-Day System Works", toc_map["welcome"], "chapter"))
        entries.append(("", "Why You Can\u2019t Focus (It\u2019s Not Your Fault)", toc_map["problem"], "chapter"))
        part_titles = {0: "Part I \u2014 The Reset  ·  Days 1\u20137", 1: "Part II \u2014 The Engine  ·  Days 8\u201321", 2: "Part III \u2014 The Armor  ·  Days 22\u201330"}
        roman = {0: "I", 1: "II", 2: "III"}
        last_part = None
        for i, ch in enumerate(CHAPTERS):
            pi = i // 3
            if pi != last_part:
                entries.append((None, part_titles[pi], None, "part"))
                last_part = pi
            entries.append((ch["num"], ch["title"], toc_map[f"ch{i}"], "chapter"))
        entries.append((None, "The 30-Day Blueprint \u2014 Day by Day", toc_map["plan"], "part"))
        entries.append(("A", "Toolkit: Planner, Tracker, Weekly Review", toc_map["toolkit"], "chapter"))
        entries.append(("", "Your Next Steps + Free Companion Kit", toc_map["resources"], "chapter"))
    book.toc_page(entries); book.page_no = 4
    # 5 welcome
    book.content_page(WELCOME["label"], "DAY 0")
    toc = book.page_no
    book.render_blocks(WELCOME["blocks"])
    # 6 problem
    book.content_page(PROBLEM["label"], "THE DIAGNOSIS")
    toc_map["welcome"] = toc
    toc = book.page_no
    book.render_blocks(PROBLEM["blocks"])
    toc_map["problem"] = toc
    # chapters
    romans = ["PART I \u2014 THE RESET", "PART II \u2014 THE ENGINE", "PART III \u2014 THE ARMOR"]
    romanshort = ["I", "II", "III"]
    subtitles = [
        "Seven days to strip friction out of your world, so focus stops being a fight and becomes the default.",
        "Install the engine: deep-work blocks that produce real output and tiny habits that run without motivation.",
        "Armor up: tame the phone, tune the biology, and relapse-proof the whole system for life.",
    ]
    for i, ch in enumerate(CHAPTERS):
        pi = i // 3
        if i % 3 == 0:
            book.part_page(romans[pi], romans[pi].split("\u2014")[1].strip().title() + " \u2014 " + ["Reset", "Engine", "Armor"][pi] if False else ["THE RESET", "THE ENGINE", "THE ARMOR"][pi], subtitles[pi], romanshort[pi])
        book.chapter_opener(ch["part"], ch["days"], ch["num"], ch["title"], ch["subtitle"], ch["bullets"])
        toc_map[f"ch{i}"] = book.page_no
        book.content_page(ch["part"], ch["days"])
        book.render_blocks(ch["blocks"])
    # blueprint pages
    intro = ("Your entire program, day by day. Each day has ONE core action \u2014 do exactly that, check the box, and let the streak carry you. "
             "Days don\u2019t need to be perfect; they need to be **consecutive enough**. Missed a day? The Never-Miss-Twice rule (Chapter 9) applies: two minutes tomorrow counts.")
    first_heading, first_rows = PLAN_WEEKS[0]
    book.plan_page(first_rows, "The 30-Day Blueprint \u2014 Day by Day", intro=intro)
    toc_map["plan"] = book.page_no
    for heading, rows in PLAN_WEEKS[1:]:
        book.plan_page(rows, heading)
    # toolkit
    book.planner_page(); 
    toc_map["toolkit"] = book.page_no
    book.tracker_page()
    book.weekly_review_page()
    # resources + closing
    book.content_page("RESOURCES", "NEXT STEPS")
    toc = book.page_no
    book.render_blocks([])  # no-op
    book.closing_placeholder = None
    # resources content
    book.h2("Your Next Steps")
    book.bullets([
        "**Print the toolkit** \u2014 the planner, tracker, and weekly review work best on paper, on your desk.",
        "**Pick your launch date** \u2014 circle it. Tell one person. Public commitment doubles follow-through.",
        "**Do Day 1 today** \u2014 one 25-minute block on your Most Important Task. That\u2019s the whole assignment.",
        "**Struggling?** Return to Chapter 6. Procrastination is a launch problem, not a character problem.",
        "**Suspect ADHD or anxiety?** This system helps \u2014 but pair it with professional support. That\u2019s strength, not weakness.",
    ])
    book.panel("FREE COMPANION KIT", "Get the printable planner pack, the digital tracker (Notion + spreadsheet), and bonus focus scripts \u2014 free for readers of this book. Link on the page where you purchased this ebook.")
    book.quote("You do not rise to the level of your goals. You fall to the level of your systems.", "James Clear, Atomic Habits")
    book.para("Thank you for trusting this book with thirty days of your life. If it helped you finish what you started, an honest review helps the next distracted reader find it \u2014 and it takes ninety seconds. That\u2019s one-tenth of a focus block. You have time.")
    book.ln(6)
    book.tracked(W / 2, book.t_y + 8, "\u2014 A. J. MERCER", 10, "Space", "B", INK, 2.4, align="C")
    toc_map["resources"] = toc
    # closing page
    book.closing()
    return book

toc_map = {}
book = render_book(toc_map)          # pass 1: discover page numbers
book2 = render_book(toc_map)         # pass 2: render TOC with real numbers
book2.output(OUT_PDF)
print("PDF written:", OUT_PDF, "pages:", book2.pages_count if hasattr(book2, "pages_count") else book2.page)
