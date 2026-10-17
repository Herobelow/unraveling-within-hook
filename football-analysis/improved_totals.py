#!/usr/bin/env python3
"""Improved match-total model (v2) built after the 17 Oct 2026 audit.

What changed vs match_total_picks.py, and why:
1. SMALL-SAMPLE SHRINKAGE (empirical-Bayes style). Early-season goals are
   mostly noise: research on early-season stats finds only ~42% of a team's
   scoring rate and ~25% of its conceding rate persists after 7 matches.
   Rates are therefore shrunk towards the league average:
       attack  = (GF + 4 x league_avg) / (played + 4)
       defence = (GA + 6 x league_avg) / (played + 6)   (defence shrunk harder)
   This stops one freak result (e.g. a 7-0 or 5-0) from dominating a rating.
2. Dixon-Coles LOW-SCORE CORRECTION (rho = -0.10). Plain Poisson
   under-estimates 0-0 and 1-1; the correction moves probability onto those
   scorelines (literature: Dixon & Coles 1997; typical rho -0.03..-0.13).
   Both flagged misses (1-0 and 1-1) sit exactly in those cells.
3. STRICTER, HONEST LINES. OVER now means MORE THAN 2 goals (total >= 3),
   because a 1-1 (total 2) lost that bet in practice. UNDER means total <= 3.
   Picks need P(total >= 3) >= 0.72 (over) or P(total <= 3) >= 0.92 (under).

No model can honestly promise 90% accuracy on over/under goals: published
benchmarks for good models are ~55-60% on O/U 2.5. The only legitimate way to
approach ~90% is to bet rarely, on extreme mismatches only, which is what
these bars do. Inputs: real tables only, as before -- nothing copied.
"""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
import independent_picks as ip

HERE = Path(__file__).resolve().parent
INPUT = HERE / "data" / "independent_inputs_54plus_japan_2026-10-17_18.json"
RHO = -0.10
K_ATT, K_DEF = 4.0, 6.0
MIN_OVER, MIN_UNDER = 0.72, 0.92
MAXG = 12

def shrunk(rate_num, played, league_avg, k):
    return (rate_num + k * league_avg) / (played + k)

def team_xg(team, opp, league_avg, venue_factor):
    att = shrunk(team["gf"], team["played"], league_avg, K_ATT)
    dfn = shrunk(opp["ga"], opp["played"], league_avg, K_DEF)
    return att * dfn / league_avg * venue_factor * team.get("attack_adj", 1.0)

def scoreline_probs(lh, la):
    """Dixon-Coles adjusted scoreline grid; returns total-goals probabilities."""
    ph = [math.exp(-lh)]; pa = [math.exp(-la)]
    for k in range(1, MAXG + 1):
        ph.append(ph[-1] * lh / k); pa.append(pa[-1] * la / k)
    tau = {(0, 0): 1 - lh * la * RHO, (1, 0): 1 + la * RHO,
           (0, 1): 1 + lh * RHO, (1, 1): 1 - RHO}
    grid = {}
    total = 0.0
    for x in range(MAXG + 1):
        for y in range(MAXG + 1):
            p = ph[x] * pa[y] * tau.get((x, y), 1.0)
            grid[x + y] = grid.get(x + y, 0.0) + p
            total += p
    return {k: v / total for k, v in grid.items()}

def analyse(data):
    out = []
    for m in data["matches"]:
        lg = m["league_goals_per_match"] / 2.0
        xh = team_xg(m["home"], m["away"], lg, data["home_factor"])
        xa = team_xg(m["away"], m["home"], lg, data["away_factor"])
        tp = scoreline_probs(xh, xa)
        p_ge3 = sum(v for k, v in tp.items() if k >= 3)
        p_le3 = sum(v for k, v in tp.items() if k <= 3)
        out.append({"id": m["id"], "competition": m["competition"], "kickoff_utc": m["kickoff_utc"],
                    "match": f"{m['home']['team']} v {m['away']['team']}",
                    "home_xg": xh, "away_xg": xa, "lambda_total": xh + xa,
                    "p_ge_3": p_ge3, "p_le_3": p_le3, "p_eq_2": tp.get(2, 0.0),
                    "home_record": f"{m['home']['gf']} scored / {m['home']['ga']} conceded in {m['home']['played']}",
                    "away_record": f"{m['away']['gf']} scored / {m['away']['ga']} conceded in {m['away']['played']}"})
    return out

def select(rows):
    over = sorted((r for r in rows if r["p_ge_3"] >= MIN_OVER), key=lambda r: -r["p_ge_3"])
    under = sorted((r for r in rows if r["p_le_3"] >= MIN_UNDER), key=lambda r: -r["p_le_3"])
    return over, under

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=INPUT)
    ap.add_argument("--out", type=Path, default=HERE / "output")
    args = ap.parse_args(argv)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    rows = analyse(data)
    over, under = select(rows)
    print(f"Matches: {len(rows)}  OVER (3+): {len(over)}  UNDER (<=3): {len(under)}")
    for r in over: print(f" OVER  P3+ {r['p_ge_3']*100:.1f}%  xGtot {r['lambda_total']:.2f}  {r['match']} [{r['competition']} · {r['kickoff_utc']}]")
    for r in under: print(f" UNDER P<=3 {r['p_le_3']*100:.1f}%  xGtot {r['lambda_total']:.2f}  {r['match']} [{r['competition']} · {r['kickoff_utc']}]")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

def write_pdf(rows, path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=15, leading=18, spaceAfter=4)
    sub = ParagraphStyle("s", parent=ss["Normal"], fontSize=8.8, leading=11.5, spaceAfter=4)
    cell = ParagraphStyle("c", parent=ss["Normal"], fontSize=7.4, leading=9.2)
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white, alignment=TA_CENTER, fontSize=8)
    h2 = ParagraphStyle("h2", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=3)
    small = ParagraphStyle("sm", parent=ss["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#444444"))

    story = [Paragraph("Recheck & improved model v2 — match totals (both teams combined)", title),
        Paragraph("<b>Flagged results:</b> FC Gifu v Fukushima United FC finished <b>1–0</b> and Tochigi City v Yokohama FC "
                  "finished <b>1–1</b>. Both were OVER picks and both missed on a 'more than 2 goals' line. "
                  "Tochigi's 2 goals only satisfied the looser '2 or more' wording — that wording is now dropped: "
                  "OVER means total &ge; 3, UNDER means total &le; 3.", sub),
        Paragraph("<b>What the first model missed</b> (found in the recheck): (1) It trusted 9–10-game scoring rates at face "
                  "value — early-season goals are mostly noise, so one freak result (e.g. Gifu's 7–0, Tochigi City's 5–0) "
                  "badly inflated a team's rating. (2) Plain Poisson under-prices exactly the scorelines that occurred: "
                  "0–0 and 1–1. (3) It used overall goals for/against with no regression to the league mean and no "
                  "home/away split. (4) It labelled 85–96% probabilities on that shaky base — overconfident.", sub),
        Paragraph("<b>Fixes in v2:</b> (a) shrinkage of every team's scoring rate (4-game prior) and conceding rate "
                  "(6-game prior) towards the league average; (b) Dixon–Coles low-score correction (rho = −0.10), which "
                  "moves probability onto 0–0/1–1; (c) much stricter bars: OVER needs P(total &ge; 3) &ge; 72%, UNDER needs "
                  "P(total &le; 3) &ge; 92%. Under v2 the Tochigi match is <b>no longer a pick at all</b> (68.3%). "
                  "Gifu still rated high (80.1%) and still lost — even a genuine 80% chance fails 1 time in 5.", sub),
        Paragraph("<b>On 'at least 90% accuracy':</b> no honest model can promise that on goals markets. Published "
                  "benchmarks put good over/under models at roughly 55–60% accuracy overall, and Dixon–Coles improves on "
                  "plain Poisson by only ~1–3%. The only legitimate route towards ~90% is to pick extremely rarely, only "
                  "where the computed probability itself is around 90%+ — and even then, 1 in 10 such picks fails. "
                  "Any sheet promising 90% across many matches is not being straight with you. This sheet therefore "
                  "lists very few picks rather than many.", sub)]

    sun = [r for r in rows if r["kickoff_utc"].startswith("Sun")]
    body = [[Paragraph("Sunday match (not yet played)", head), Paragraph("xG total", head),
             Paragraph("P(total 3+)", head), Paragraph("P(total ≤3)", head), Paragraph("v2 verdict", head)]]
    for r in sorted(sun, key=lambda r: -max(r["p_ge_3"], r["p_le_3"])):
        if r["p_ge_3"] >= MIN_OVER: v = "<b>OVER pick</b>"
        elif r["p_le_3"] >= MIN_UNDER: v = "<b>UNDER pick</b>"
        else: v = "No pick — not confident enough"
        body.append([Paragraph(f"{r['match']}<br/><font color='#555555'>{r['competition']} · {r['kickoff_utc']}</font>", cell),
                     Paragraph(f"{r['lambda_total']:.2f}", cell), Paragraph(f"{r['p_ge_3']*100:.1f}%", cell),
                     Paragraph(f"{r['p_le_3']*100:.1f}%", cell), Paragraph(v, cell)])
    t = Table(body, colWidths=[77*mm, 25*mm, 35*mm, 35*mm, 105*mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#555555")),
                           ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                           ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#f7f7f7"), colors.white]),
                           ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#bbbbbb")),
                           ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]))
    story += [Paragraph("Revised v2 ratings — remaining Sunday 18 Oct matches", h2), t,
              Paragraph("No Sunday match clears the v2 bars, so the honest revised sheet has <b>no new confident pick</b> "
                        "for Sunday. The closest are SC Cambuur v AZ Alkmaar (64.8% for 3+) and Machida Zelvia v Avispa "
                        "Fukuoka (64.3%) — both well short of the bar, so both are dropped.", sub),
              Spacer(1, 6),
              Paragraph("Method sources: Dixon & Coles (1997) low-score correction; early-season shrinkage research "
                        "(only ~42% of a team's early scoring rate and ~25% of its conceding rate persists); published "
                        "over/under model benchmarks (~55–60%). Inputs remain real league tables only — no copied "
                        "predictions. Analysis only, not betting advice.", small)]
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm,
                            topMargin=9*mm, bottomMargin=9*mm, title="Recheck and improved model v2", author="football-analysis")
    doc.build(story)
