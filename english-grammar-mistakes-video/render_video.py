#!/usr/bin/env python3
"""Render the '5 English Grammar Mistakes' video to MP4.

Draws frames with Pillow, pipes raw RGB to ffmpeg, and muxes a synthesized
soundtrack (music bed + SFX). Usage:

    python3 render_video.py [--start SS] [--end SS] [--out PATH] [--fps N]
"""
import os, sys, math, argparse, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FD = os.path.join(ROOT, "discipline-blueprint/build/assets/fonts")
OUTDIR = os.path.dirname(os.path.abspath(__file__))

W, H, FPS, DUR, SR = 1280, 720, 24, 340.0, 44100

# ---------------------------------------------------------------- fonts
def f(path, size):
    return ImageFont.truetype(os.path.join(FD, path), size)

F_BIG    = f("space-grotesk-latin-700-normal.ttf", 116)
F_TITLE  = f("space-grotesk-latin-700-normal.ttf", 78)
F_HEAD   = f("space-grotesk-latin-700-normal.ttf", 54)
F_BODY   = f("inter-latin-600-normal.ttf", 40)
F_BODYB  = f("inter-latin-800-normal.ttf", 40)
F_SM     = f("inter-latin-600-normal.ttf", 32)
F_SMW    = f("inter-latin-800-normal.ttf", 32)
F_NUM    = f("space-grotesk-latin-700-normal.ttf", 150)
F_SYM    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)

# ---------------------------------------------------------------- palette
NAVY=(15,23,42); NAVY2=(30,41,59); PANEL=(34,47,74); PANEL2=(45,61,94)
GOLD=(245,197,24); WHITE=(248,250,252); MUTED=(148,163,184)
RED=(248,68,68); GREEN=(52,211,153); BLUE=(96,165,250); AMBER=(251,146,60)
SKIN=(255,214,170); HAIR=(52,38,28)

ALEX_SKIN=(255,214,170); ALEX_HAIR=(52,38,28); ALEX_SHIRT=(59,130,246)
MAY_SKIN=(255,222,180); MAY_HAIR=(24,90,80); MAY_SHIRT=(16,185,129)

_c = lambda c, a=255: (c[0], c[1], c[2], int(round(a)))

# ---------------------------------------------------------------- helpers
def text(d, xy, s, font, fill, anchor="mm", stroke=0, sfill=None):
    d.text(xy, s, font=font, fill=fill, anchor=anchor,
           stroke_width=stroke, stroke_fill=sfill)

def tw(d, s, font):
    return d.textlength(s, font=font)

def wrap(d, s, font, maxw):
    lines, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [""]

def rrect(d, box, r, fill=None, outline=None, ow=0):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=ow)

def a(t, dur, start=0.0):
    return min(1.0, max(0.0, (t - start) / dur))

def ease(x):
    return 1 - (1 - x) ** 3

# ---------------------------------------------------------------- background
def make_bg():
    y = np.linspace(0, 1, H)[:, None]
    top = np.array([17,27,52]); bot = np.array([7,11,26])
    g = (top[None, None, :] * (1 - y[..., None]) + bot[None, None, :] * y[..., None])
    arr = np.repeat(g, W, axis=1).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")

BG = make_bg()

def draw_bg(d, t):
    # drifting translucent bubbles
    for i in range(9):
        ph = i * 1.31
        bx = (math.sin(t * 0.22 + ph) * 0.5 + 0.5) * W
        by = ((t * (14 + i * 5) * 0.02 + ph) % 1.15 - 0.12) * H
        r = 22 + (i * 11) % 46
        d.ellipse([bx-r, by-r, bx+r, by+r], outline=(90,110,150,40), width=3)
    # header badge
    rrect(d, [40, 26, 470, 74], 24, fill=_c(PANEL, 200), outline=_c(GOLD, 180), ow=2)
    text(d, (68, 50), "English Grammar for Beginners", F_SMW, _c(GOLD))
    # top-right channel mark
    text(d, (W-40, 50), "5 Mistakes", F_SM, _c(MUTED,220), anchor="rm")

# ---------------------------------------------------------------- characters
def person(d, cx, cy, s, skin, hair, shirt, expr="smile", alpha=255):
    a_ = alpha
    # body
    bw, bh = 70*s, 96*s
    rrect(d, [cx-bw/2, cy-10*s, cx+bw/2, cy+bh], 30*s, fill=_c(shirt, a_))
    # arms
    d.line([cx-bw/2, cy+14*s, cx-bw/2-26*s, cy+44*s], fill=_c(shirt,a_), width=int(20*s))
    d.line([cx+bw/2, cy+14*s, cx+bw/2+26*s, cy+44*s], fill=_c(shirt,a_), width=int(20*s))
    # neck
    d.rectangle([cx-12*s, cy-22*s, cx+12*s, cy+2*s], fill=_c(skin,a_))
    # head
    hr = 46*s
    d.ellipse([cx-hr, cy-hr-26*s, cx+hr, cy+hr-26*s], fill=_c(skin,a_))
    # hair
    d.chord([cx-hr, cy-hr-26*s, cx+hr, cy+hr-26*s], 180, 360, fill=_c(hair,a_))
    ey = cy - 26*s + 8*s
    ex = hr*0.42
    if expr == "shock":
        d.ellipse([cx-ex-9*s, ey-9*s, cx-ex+9*s, ey+9*s], fill=_c(NAVY,a_))
        d.ellipse([cx+ex-9*s, ey-9*s, cx+ex+9*s, ey+9*s], fill=_c(NAVY,a_))
        d.ellipse([cx-10*s, cy+14*s, cx+10*s, cy+26*s], outline=_c(NAVY,a_), width=int(4*s))
    elif expr == "wink":
        d.ellipse([cx-ex-7*s, ey-7*s, cx-ex+7*s, ey+7*s], fill=_c(NAVY,a_))
        d.line([cx+ex-8*s, ey, cx+ex+8*s, ey], fill=_c(NAVY,a_), width=int(5*s))
        d.arc([cx-14*s, cy+8*s, cx+14*s, cy+24*s], 20, 160, fill=_c(NAVY,a_), width=int(5*s))
    else:
        d.ellipse([cx-ex-7*s, ey-7*s, cx-ex+7*s, ey+7*s], fill=_c(NAVY,a_))
        d.ellipse([cx+ex-7*s, ey-7*s, cx+ex+7*s, ey+7*s], fill=_c(NAVY,a_))
        d.arc([cx-14*s, cy+10*s, cx+14*s, cy+26*s], 20, 160, fill=_c(NAVY,a_), width=int(5*s))

def bubble(d, cx, cy, w, h, lines, font, tcol, fill=WHITE, alpha=255, tail="up"):
    rrect(d, [cx-w/2, cy-h/2, cx+w/2, cy+h/2], 26, fill=_c(fill, alpha),
          outline=_c(NAVY2, alpha), ow=3)
    if tail == "up":
        d.polygon([(cx-16, cy+h/2-2), (cx+16, cy+h/2-2), (cx, cy+h/2+30)],
                  fill=_c(fill, alpha))
        d.line([(cx-16, cy+h/2-2), (cx, cy+h/2+30)], fill=_c(NAVY2,alpha), width=3)
        d.line([(cx+16, cy+h/2-2), (cx, cy+h/2+30)], fill=_c(NAVY2,alpha), width=3)
    else:
        d.polygon([(cx-16, cy-h/2+2), (cx+16, cy-h/2+2), (cx, cy-h/2-30)],
                  fill=_c(fill, alpha))
    lh = font.size + 12
    y0 = cy - (len(lines)-1)*lh/2
    for i, ln in enumerate(lines):
        text(d, (cx, y0 + i*lh), ln, font, _c(tcol, alpha))

def big_sentence(d, cx, cy, s, font, col, alpha=255, stroke=0):
    text(d, (cx, cy), s, font, _c(col, alpha), stroke=stroke, sfill=_c(NAVY, alpha))

# ---------------------------------------------------------------- tracker
def draw_tracker(d, filled, alpha=255, big=False):
    y = H - 152 if not big else H - 178
    x = W/2 - (5*96)/2
    for i in range(5):
        bx = x + i*110
        ok = i < filled
        rrect(d, [bx, y, bx+84, y+84], 20,
              fill=_c(GREEN, alpha if ok else 0),
              outline=_c(GOLD if ok else (60,75,105), alpha), ow=3)
        if ok:
            text(d, (bx+42, y+42), str(i+1), F_HEAD, _c(NAVY, alpha))

# ---------------------------------------------------------------- scenes
def scene_hook(d, t):
    # 0-4 title
    if t < 4:
        k = ease(a(t, 0.5))
        rrect(d, [120, 250, W-120, 470], 36, fill=_c(PANEL,255*k), outline=_c(RED,255*k), ow=6)
        big_sentence(d, W/2, 330, "5 ENGLISH MISTAKES", F_BIG, RED, alpha=255*k)
        big_sentence(d, W/2, 440, "YOU MIGHT MAKE", F_BIG, GOLD, alpha=255*k)
        return
    beats = [(4,9,"I AM AGREE","I AGREE"),
             (9,14,"She DON'T like it","She DOESN'T like it"),
             (14,19,"I DIDN'T WENT","I DIDN'T GO")]
    for (s0,s1,w,c) in beats:
        if s0 <= t < s1:
            lt = t - s0
            g = lt > 3.0
            col = GREEN if g else RED
            wig = math.sin(t*18)*8 if g else 0
            rrect(d, [120, 240, W-120, 480], 36, fill=_c(PANEL,255), outline=_c(col,255), ow=6)
            big_sentence(d, W/2 + wig, 355, c if g else w, F_BIG, col)
            person(d, W/2, 545, 1.5, MAY_SKIN, MAY_HAIR, MAY_SHIRT,
                   "shock" if not g else "smile")
            return
    # teaser
    wig = math.sin(t*12)*10
    rrect(d, [140, 240, W-140, 480], 36, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=6)
    big_sentence(d, W/2+wig, 345, "#5", F_BIG, GOLD)
    big_sentence(d, W/2+wig, 440, "a mistake you make EVERY day", F_HEAD, WHITE)

def scene_setup(d, t):
    if t < 9.5:
        person(d, 380, 400, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        person(d, 900, 400, 1.9, MAY_SKIN, MAY_HAIR, MAY_SHIRT, "smile")
        text(d, (380, 560), "ALEX", F_SMW, _c(BLUE))
        text(d, (900, 560), "MAYA", F_SMW, _c(GREEN))
        k = ease(a(t,0.6))
        rrect(d, [190, 170, W-190, 300], 30, fill=_c(PANEL,255*k), outline=_c(GOLD,255*k), ow=4)
        big_sentence(d, W/2, 235, "Meet Alex and Maya", F_TITLE, WHITE, alpha=255*k)
    else:
        lt = t - 9.5
        rrect(d, [140, 190, W-140, 440], 36, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=6)
        big_sentence(d, W/2, 270, "Can YOU catch all 5?", F_BIG, WHITE)
        big_sentence(d, W/2, 350, "Spot the grammar mistakes", F_HEAD, MUTED)
        big_sentence(d, W/2, 400, "before Maya does!", F_HEAD, GOLD)
        draw_tracker(d, 0, big=True)

def lesson_intro(d, t, wrong, correct, rule, exs, wts):
    """Shared skeleton for the five mistakes."""
    # phase map keyed by local time
    pass

def scene_lesson1(d, t):
    if t < 5:
        person(d, 360, 470, 1.8, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, 620, 300, 470, 130, ["I am agree with you!"], F_BODYB, RED)
    elif t < 9:
        person(d, 900, 470, 1.8, MAY_SKIN, MAY_HAIR, MAY_SHIRT, "wink")
        bubble(d, 560, 300, 470, 130, ['Wait! Just say, "I agree with you."'], F_BODYB, GREEN)
    elif t < 14:
        rrect(d, [150, 230, W-150, 470], 32, fill=_c(PANEL,255), outline=_c(BLUE,255), ow=5)
        text(d, (W/2, 300), "Rule", F_SMW, _c(BLUE))
        big_sentence(d, W/2, 365, "Agree = verb.  No \"am\".", F_HEAD, WHITE)
    elif t < 18:
        rrect(d, [150, 230, W-150, 470], 32, fill=_c(PANEL,255), outline=_c(GREEN,255), ow=5)
        big_sentence(d, W/2, 355, "I am agree", F_BIG, RED)
        big_sentence(d, W/2, 440, "I agree", F_BIG, GREEN)
    elif t < 23:
        rrect(d, [150, 230, W-150, 470], 32, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=5)
        big_sentence(d, W/2, 300, "Which is correct?", F_HEAD, WHITE)
        big_sentence(d, W/2, 400, '"I agree"  or  "I am agree"?', F_BODYB, GOLD)
    else:
        k = ease(a(t, 24.5, 23))
        person(d, W/2, 420, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, W/2, 220, 520, 120, ["\"I agree!\"", "No \"am\"."], F_BODYB, GREEN, alpha=255*k)
    if t >= 24.5:
        draw_tracker(d, 1, big=True)

def scene_lesson2(d, t):
    if t < 5:
        person(d, 360, 470, 1.8, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, 640, 300, 460, 120, ["She don't play football."], F_BODYB, RED)
    elif t < 9:
        person(d, 900, 470, 1.8, MAY_SKIN, MAY_HAIR, MAY_SHIRT, "wink")
        bubble(d, 600, 300, 460, 120, ["She doesn't play football!"], F_BODYB, GREEN)
    elif t < 16:
        rrect(d, [150, 200, W-150, 420], 32, fill=_c(PANEL,255), outline=_c(BLUE,255), ow=5)
        text(d, (W/2, 250), "With he / she / it  ->  doesn't", F_HEAD, _c(BLUE))
        big_sentence(d, W/2, 340, "He doesn't run.", F_HEAD, WHITE)
        big_sentence(d, W/2, 400, "It doesn't work.", F_HEAD, WHITE)
    elif t < 23:
        person(d, 400, 430, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, 760, 300, 420, 120, ["She don't...", "wait! She doesn't!"], F_BODYB, GREEN)
    else:
        person(d, W/2, 430, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "wink")
        bubble(d, W/2, 220, 520, 120, ["She doesn't play football.", "\"doesn't\" for he/she/it"], F_BODYB, GREEN, alpha=255)
    if t >= 24.5:
        draw_tracker(d, 2, big=True)

def scene_lesson3(d, t):
    if t < 5:
        person(d, 360, 470, 1.8, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, 640, 300, 460, 120, ["I didn't went."], F_BODYB, RED)
    elif t < 13:
        rrect(d, [150, 190, W-150, 450], 32, fill=_c(PANEL,255), outline=_c(BLUE,255), ow=5)
        text(d, (W/2, 240), "After \"didn't\", use the base form", F_HEAD, _c(BLUE))
        big_sentence(d, W/2, 330, "go   eat   see", F_BIG, WHITE)
        big_sentence(d, W/2, 410, "not  went   ate   saw", F_HEAD, RED)
    elif t < 18:
        rrect(d, [150, 230, W-150, 470], 32, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=5)
        big_sentence(d, W/2, 320, "Mini-quiz", F_SMW, _c(GOLD))
        big_sentence(d, W/2, 390, "I didn't ___ breakfast.", F_HEAD, WHITE)
        big_sentence(d, W/2, 450, "Eat    or    ate?", F_BODYB, GOLD)
    elif t < 21:
        n = int(math.ceil(21 - t))
        big_sentence(d, W/2, 350, str(n), F_NUM, GOLD)
    elif t < 26:
        big_sentence(d, W/2, 350, "ate", F_BIG, RED)
        d.line([W/2-140, 360, W/2+140, 360], fill=_c(RED,255), width=8)
        big_sentence(d, W/2, 440, "eat", F_BIG, GREEN)
    else:
        person(d, W/2, 430, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, W/2, 220, 560, 120, ["I didn't eat breakfast.", "base form: eat"], F_BODYB, GREEN)
    if t >= 26:
        draw_tracker(d, 3, big=True)

def scene_lesson4(d, t):
    if t < 5:
        person(d, 360, 470, 1.8, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, 660, 300, 420, 120, ["I have 25 years."], F_BODYB, RED)
    elif t < 12:
        rrect(d, [150, 200, W-150, 430], 32, fill=_c(PANEL,255), outline=_c(BLUE,255), ow=5)
        text(d, (W/2, 250), "Age uses \"be\", not \"have\"", F_HEAD, _c(BLUE))
        big_sentence(d, W/2, 340, "I am 25 years old.", F_HEAD, WHITE)
        big_sentence(d, W/2, 400, "She is 30 years old.", F_HEAD, WHITE)
    else:
        person(d, W/2, 430, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "wink")
        bubble(d, W/2, 220, 540, 120, ["I am 25 years old!", "age = be, not have"], F_BODYB, GREEN)
    if t >= 13:
        draw_tracker(d, 4, big=True)

def scene_lesson5(d, t):
    if t < 5:
        person(d, 360, 470, 1.8, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        bubble(d, 660, 300, 440, 120, ["He go to school", "every day."], F_BODYB, RED)
    elif t < 13:
        rrect(d, [150, 190, W-150, 450], 32, fill=_c(PANEL,255), outline=_c(BLUE,255), ow=5)
        text(d, (W/2, 240), "he / she / it  ->  add -s / -es", F_HEAD, _c(BLUE))
        big_sentence(d, W/2, 330, "She works.   He watches TV.", F_HEAD, WHITE)
        big_sentence(d, W/2, 400, "It rains.", F_HEAD, WHITE)
    elif t < 22:
        rrect(d, [150, 230, W-150, 470], 32, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=5)
        big_sentence(d, W/2, 320, "Help Alex!", F_SMW, _c(GOLD))
        big_sentence(d, W/2, 400, "He ___ to school every day.", F_HEAD, WHITE)
        person(d, 360, 560, 1.3, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "shock")
    elif t < 27:
        big_sentence(d, W/2, 350, "He goes to school every day!", F_HEAD, GREEN)
        d.line([W/2-160, 360, W/2+160, 360], fill=_c(GREEN,255), width=8)
    else:
        person(d, 380, 430, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        person(d, 900, 430, 1.9, MAY_SKIN, MAY_HAIR, MAY_SHIRT, "wink")
        bubble(d, 640, 230, 440, 110, ["He goes to school", "every day!"], F_BODYB, GREEN)
    if t >= 27:
        draw_tracker(d, 5, big=True)

def scene_rapid(d, t):
    if t < 5:
        rrect(d, [150, 200, W-150, 430], 32, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=5)
        big_sentence(d, W/2, 270, "Rapid-fire challenge!", F_TITLE, WHITE)
        big_sentence(d, W/2, 360, "Correct each sentence", F_HEAD, MUTED)
        # ticking clock
        ang = math.radians((t/5)*360)
        d.ellipse([W/2-52, 380-52, W/2+52, 380+52], outline=_c(GOLD,255), width=6)
        d.line([W/2, 380, W/2+math.cos(ang)*42, 380+math.sin(ang)*42], fill=_c(GOLD,255), width=5)
        return
    qs = [("She don't understand.", "She doesn't understand."),
          ("I didn't saw him.", "I didn't see him."),
          ("He play football every day.", "He plays football every day.")]
    qi = int((t-5)//8.0)
    if qi >= 3:
        rrect(d, [150, 230, W-150, 470], 32, fill=_c(PANEL,255), outline=_c(GOLD,255), ow=5)
        big_sentence(d, W/2, 330, "How many did you get?", F_TITLE, WHITE)
        big_sentence(d, W/2, 410, "Share your score!", F_HEAD, GOLD)
        return
    q, c = qs[qi]
    lt = t - 5 - qi*8
    # scoreboard top-right
    rrect(d, [W-300, 40, W-40, 120], 20, fill=_c(PANEL,230), outline=_c(GOLD,200), ow=3)
    text(d, (W-170, 62), "Scoreboard", F_SMW, _c(GOLD))
    text(d, (W-170, 100), f"Q{qi+1} / 3", F_BODYB, WHITE)
    if lt < 3.5:
        rrect(d, [150, 240, W-150, 460], 32, fill=_c(PANEL,255), outline=_c(RED,255), ow=5)
        big_sentence(d, W/2, 340, q, F_HEAD, RED)
        text(d, (W/2, 420), "Your turn...", F_SM, _c(MUTED))
    else:
        rrect(d, [150, 240, W-150, 460], 32, fill=_c(PANEL,255), outline=_c(GREEN,255), ow=5)
        big_sentence(d, W/2, 330, q, F_SM, RED)
        big_sentence(d, W/2, 400, c, F_HEAD, GREEN)
        text(d, (W/2, 450), "correct!", F_SMW, GREEN)

def scene_outro(d, t):
    if t < 7:
        person(d, 420, 430, 1.9, ALEX_SKIN, ALEX_HAIR, ALEX_SHIRT, "smile")
        person(d, 860, 430, 1.9, MAY_SKIN, MAY_HAIR, MAY_SHIRT, "wink")
        bubble(d, 640, 200, 480, 120, ["Subscribe for the", "next lesson!"], F_BODYB, GOLD)
    rrect(d, [150, 250, W-150, 420], 36, fill=_c(PANEL,255), outline=_c(GREEN,255), ow=6)
    big_sentence(d, W/2, 310, "Thanks for watching!", F_TITLE, WHITE)
    big_sentence(d, W/2, 375, "Next: \"Say These 10 English", F_BODYB, GOLD)
    big_sentence(d, W/2, 415, "Sentences Correctly!\"", F_BODYB, GOLD)
    # subscribe button
    rrect(d, [W/2-150, 490, W/2+150, 560], 35, fill=_c(RED,255))
    big_sentence(d, W/2, 525, "SUBSCRIBE", F_BODYB, WHITE)

# ---------------------------------------------------------------- frame
def render_frame(t):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img = Image.alpha_composite(BG.copy(), img)
    d = ImageDraw.Draw(img, "RGBA")
    draw_bg(d, t)
    if t < 15: scene_hook(d, t)
    elif t < 35: scene_setup(d, t)
    elif t < 80: scene_lesson1(d, t)
    elif t < 125: scene_lesson2(d, t)
    elif t < 170: scene_lesson3(d, t)
    elif t < 215: scene_lesson4(d, t)
    elif t < 265: scene_lesson5(d, t)
    elif t < 315: scene_rapid(d, t)
    else: scene_outro(d, t)
    return img.convert("RGB")

# ---------------------------------------------------------------- audio
def build_audio():
    n = int(DUR * SR)
    out = np.zeros(n, dtype=np.float32)

    def add(sig, t0):
        i = int(t0 * SR)
        j = min(n, i + len(sig))
        if i < n:
            out[i:j] += sig[:j-i]

    def note(freq, dur, t0, amp, kind="sine", decay=None):
        tt = np.arange(int(dur*SR)) / SR
        if kind == "sine":
            v = np.sin(2*np.pi*freq*tt)
        elif kind == "pluck":
            v = np.sin(2*np.pi*freq*tt) * np.exp(-tt*4)
        elif kind == "saw":
            v = 2*(tt*freq % 1) - 1
        else:
            v = np.sign(np.sin(2*np.pi*freq*tt))
        if decay is not None:
            v = v * np.exp(-tt*decay)
        add(v.astype(np.float32)*amp, t0)

    # music bed: 4-bar loop, C - Am - F - G
    prog = [(130.81, [261.63, 329.63, 392.0]),
            (110.0, [220.0, 261.63, 329.63]),
            (87.31, [174.61, 220.0, 261.63]),
            (98.0,  [196.0, 246.94, 293.66])]
    beat = 0.42
    bar = beat*4
    nb = int(DUR/bar)
    for b in range(nb):
        root, chord = prog[b % 4]
        t0 = b*bar
        note(root, bar*0.9, t0, 0.09, "sine", decay=0.6)
        for k in range(8):
            f = chord[k % 3] * (2 if k >= 4 else 1)
            note(f, 0.32, t0 + k*beat, 0.035, "pluck")

    # SFX
    def ding(t0, f=880.0, amp=0.16):
        note(f, 0.45, t0, amp, "sine", decay=2.4)
        note(f*1.5, 0.35, t0, amp*0.6, "sine", decay=3.0)

    def buzz(t0):
        note(150.0, 0.3, t0, 0.13, "saw", decay=9)

    def tick(t0):
        note(1400.0, 0.05, t0, 0.09, "sine", decay=60)

    def pop(t0):
        note(520.0, 0.18, t0, 0.13, "sine", decay=14)

    def fanfare(t0):
        for i, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
            note(f, 0.28, t0 + i*0.13, 0.15, "sine", decay=3.2)

    def whoosh(t0):
        note(300.0, 0.35, t0, 0.10, "sine", decay=5)

    # hook
    for tt in [0.6, 3.6, 6.6, 9.6]: buzz(tt)
    for tt in [4.3, 7.3, 10.3]: ding(tt, 988.0)
    ding(12.4, 1175.0, 0.18); pop(12.4)
    ding(15.5, 659.25); pop(15.5)
    # lessons
    buzz(35.4); ding(40.1); ding(44.2)
    buzz(49.0); ding(49.9); ding(53.2)
    fanfare(58.0)
    buzz(80.4); ding(85.1); ding(89.2)
    buzz(96.0); whoosh(98.6); ding(99.4)
    buzz(125.4); ding(129.6)
    tick(145.4); tick(146.6); tick(147.8)
    whoosh(148.6); ding(149.4); fanfare(152.0)
    buzz(170.4); ding(174.0); ding(178.0)
    buzz(215.4); ding(219.6); ding(226.0)
    buzz(238.0); tick(240.0); tick(241.0)
    fanfare(243.5); pop(246.0)
    # rapid
    tick(270.0); tick(271.0); tick(272.0)
    ding(274.0); ding(278.2); ding(282.4)
    ding(286.0); ding(290.0); ding(294.0)
    fanfare(296.0)
    ding(316.0); pop(326.0); ding(332.0)

    out = np.clip(out, -1, 1)
    return (out * 32000).astype(np.int16)

def write_wav(path):
    import wave
    pcm = build_audio()
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DUR)
    ap.add_argument("--out", default=os.path.join(OUTDIR, "5-english-grammar-mistakes.mp4"))
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--audio", default=None)
    args = ap.parse_args()

    from imageio_ffmpeg import get_ffmpeg_exe
    ff = get_ffmpeg_exe()
    wav = args.audio or os.path.join(OUTDIR, "_soundtrack.wav")
    print("building soundtrack...", flush=True)
    write_wav(wav)
    print("rendering video...", flush=True)

    dur = args.end - args.start
    nfr = int(dur * args.fps)
    cmd = [ff, "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(args.fps), "-i", "-",
           "-i", wav, "-ss", f"{args.start:.3f}", "-t", f"{dur:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "22",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", "-shortest", args.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(nfr):
        t = args.start + (i + 0.5) / args.fps
        fr = render_frame(t)
        proc.stdin.write(fr.tobytes())
        if i % 240 == 0:
            print(f"  frame {i}/{nfr}  t={t:.1f}s", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done ->", args.out, flush=True)

if __name__ == "__main__":
    main()
