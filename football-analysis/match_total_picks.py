#!/usr/bin/env python3
"""Match-TOTAL goal picks (combined goals of BOTH teams), 17-18 Oct 2026.

This implements the reading the user confirmed on 17 Oct 2026:
  OVER side  = both teams together score a total of 2 goals or more  -> P(total >= 2)
  BELOW side = both teams together score a total of 3 goals or below -> P(total <= 3)

It replaces the earlier single-team reading (one team scoring 3+ / 0-2).

Same independent model as independent_picks.py, nothing copied: each team's
expected goals come from real goals scored/conceded this season, the league's
goals-per-match average, venue factor and confirmed-news adjustment only.
Match total lambda = home xG + away xG; total goals ~ Poisson(lambda).

Confidence bars (only confident picks are listed, doubt is dropped):
  OVER 2+ : P(total >= 2) >= 0.85
  BELOW 3-: P(total <= 3) >= 0.85
P(total >= 3) ("more than 2") is printed alongside for transparency -- a total
of exactly 2 is the difference between the two readings.

Inputs: data/independent_inputs_54plus_japan_2026-10-17_18.json (77 matches).
Outputs: output/match_total_goal_picks_2026-10-17.pdf and .csv
Requires reportlab for the PDF only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import independent_picks as ip

HERE = Path(__file__).resolve().parent
INPUT = HERE / "data" / "independent_inputs_54plus_japan_2026-10-17_18.json"
DEFAULT_OUT = HERE / "output"
MIN_OVER2, MIN_BELOW3 = 0.85, 0.85
MAX_GOALS = 15


def total_probs(lam: float) -> dict:
    """Poisson probabilities for the combined match total."""
    if lam < 0:
        raise ValueError("lambda must be >= 0")
    pmf = [math.exp(-lam)]
    for k in range(1, MAX_GOALS + 1):
        pmf.append(pmf[-1] * lam / k)
    return {
        "p_ge_2": 1.0 - sum(pmf[:2]),   # total of 2 goals or more
        "p_ge_3": 1.0 - sum(pmf[:3]),   # more than 2 goals
        "p_le_3": sum(pmf[:4]),         # total of 3 goals or below
        "p_eq_3": pmf[3],
    }


def analyse_matches(data: dict) -> list[dict]:
    """Combine the two team lambdas from independent_picks into match totals."""
    team_rows = ip.analyse(data)
    by_match: dict[str, dict] = {}
    order = []
    for r in team_rows:
        if r["id"] not in by_match:
            by_match[r["id"]] = {}
            order.append(r["id"])
        by_match[r["id"]][r["venue"]] = r
    out = []
    for mid in order:
        h, a = by_match[mid]["home"], by_match[mid]["away"]
        lam = h["xg"] + a["xg"]
        probs = total_probs(lam)
        out.append({
            "id": mid, "competition": h["competition"], "kickoff_utc": h["kickoff_utc"],
            "match": h["match"], "home_team": h["team"], "away_team": a["team"],
            "home_xg": h["xg"], "away_xg": a["xg"], "lambda_total": lam,
            "home_record": h["record"], "away_record": a["record"],
            "league_avg": h["league_avg"], **probs,
        })
    return out


def select(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    over = sorted((r for r in rows if r["p_ge_2"] >= MIN_OVER2), key=lambda r: -r["p_ge_2"])
    below = sorted((r for r in rows if r["p_le_3"] >= MIN_BELOW3), key=lambda r: -r["p_le_3"])
    return over, below


def write_csv(rows, over, below, path: Path) -> None:
    fields = ["pick", "competition", "kickoff_utc", "match", "lambda_total", "home_xg", "away_xg",
              "p_total_2_or_more", "p_total_more_than_2", "p_total_3_or_below", "p_total_exactly_3",
              "home_team_record", "away_team_record", "league_avg_per_team"]
    picked = {id(r) for r in over + below}
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            label = "OVER (total 2+)" if r in over else "BELOW (total <=3)" if r in below else ""
            w.writerow({"pick": label, "competition": r["competition"], "kickoff_utc": r["kickoff_utc"],
                        "match": r["match"], "lambda_total": round(r["lambda_total"], 3),
                        "home_xg": round(r["home_xg"], 3), "away_xg": round(r["away_xg"], 3),
                        "p_total_2_or_more": round(r["p_ge_2"], 4),
                        "p_total_more_than_2": round(r["p_ge_3"], 4),
                        "p_total_3_or_below": round(r["p_le_3"], 4),
                        "p_total_exactly_3": round(r["p_eq_3"], 4),
                        "home_team_record": r["home_record"], "away_team_record": r["away_record"],
                        "league_avg_per_team": round(r["league_avg"], 3)})


def write_pdf(rows, over, below, path: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("reportlab is needed for the PDF: pip install reportlab") from exc

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=15, leading=18, spaceAfter=4)
    sub = ParagraphStyle("s", parent=ss["Normal"], fontSize=8.8, leading=11.5, spaceAfter=4)
    cell = ParagraphStyle("c", parent=ss["Normal"], fontSize=7.4, leading=9.2)
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white,
                          alignment=TA_CENTER, fontSize=8)
    small = ParagraphStyle("sm", parent=ss["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#444444"))
    h2 = ParagraphStyle("h2", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=3)

    story = [
        Paragraph("Match-total goals: both teams combined — weekend of 17–18 October 2026", title),
        Paragraph(
            "<b>Reading confirmed by you:</b> OVER side = the two teams together score a <b>total of 2 goals "
            "or more</b>; BELOW side = the two teams together score a <b>total of 3 goals or below</b>. This "
            "replaces the earlier single-team sheet. A total of exactly 3 goals satisfies both descriptions, "
            "so the two lists are alternatives, not a combination bet.", sub),
        Paragraph(
            "<b>Not copied from any prediction site.</b> Each team's expected goals are computed here from real "
            "events only (goals scored/conceded this season, league goals-per-match, venue, confirmed news). "
            "Match-total expected goals = home xG + away xG, total goals treated as Poisson. "
            f"<b>{len(rows)} matches evaluated. Confident picks only</b> (over: P(total &ge; 2) &ge; {MIN_OVER2:.0%}; "
            f"below: P(total &le; 3) &ge; {MIN_BELOW3:.0%}); anything with doubt is dropped. "
            "The 'more than 2' column (P(total &ge; 3)) is shown in case that stricter line is wanted. "
            "Analysis only, not betting advice.", sub),
    ]

    def section(group, heading, colour, prob_key, prob_label):
        if not group:
            return [Paragraph(heading, h2), Paragraph("No match passes the confidence bar.", sub)]
        body = [[Paragraph("#", head), Paragraph("Match", head), Paragraph(prob_label, head),
                 Paragraph("Match xG total", head), Paragraph("Also: P(more than 2)", head),
                 Paragraph("Real events behind it", head)]]
        for i, r in enumerate(group, 1):
            events = (f"{r['home_team']}: {r['home_record']}.<br/>{r['away_team']}: {r['away_record']}.<br/>"
                      f"<font color='#555555'>League avg {r['league_avg']:.2f} goals per team per game.</font>")
            body.append([Paragraph(str(i), cell),
                         Paragraph(f"<b>{r['match']}</b><br/><font color='#555555'>{r['competition']} · {r['kickoff_utc']}</font>", cell),
                         Paragraph(f"<b>{r[prob_key] * 100:.1f}%</b>", cell),
                         Paragraph(f"{r['home_xg']:.2f} + {r['away_xg']:.2f} = <b>{r['lambda_total']:.2f}</b>", cell),
                         Paragraph(f"P(3+) {r['p_ge_3'] * 100:.1f}% · P(=3) {r['p_eq_3'] * 100:.1f}%", cell),
                         Paragraph(events, cell)])
        t = Table(body, colWidths=[8 * mm, 58 * mm, 20 * mm, 38 * mm, 42 * mm, 111 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(colour)),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]))
        return [Paragraph(heading, h2), t]

    story += section(over, "OVER — both teams together score a total of 2 goals or more", "#b03a2e",
                     "p_ge_2", "P(total 2+)")
    story += section(below, "BELOW — both teams together score a total of 3 goals or below", "#1f618d",
                     "p_le_3", "P(total ≤3)")

    body = [[Paragraph("Match", head), Paragraph("Competition", head), Paragraph("xG total", head),
             Paragraph("P(total 2 or more)", head), Paragraph("P(more than 2)", head),
             Paragraph("P(total 3 or below)", head)]]
    for r in rows:
        body.append([Paragraph(r["match"], cell), Paragraph(r["competition"], cell),
                     Paragraph(f"{r['lambda_total']:.2f}", cell),
                     Paragraph(f"{r['p_ge_2'] * 100:.1f}%", cell),
                     Paragraph(f"{r['p_ge_3'] * 100:.1f}%", cell),
                     Paragraph(f"{r['p_le_3'] * 100:.1f}%", cell)])
    t = Table(body, colWidths=[77 * mm, 40 * mm, 25 * mm, 45 * mm, 45 * mm, 45 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#555555")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]))
    story += [Paragraph(f"All {len(rows)} matches evaluated", h2), t]
    story += [Spacer(1, 6), Paragraph(
        "Inputs: football-analysis/data/independent_inputs_54plus_japan_2026-10-17_18.json (real league "
        "tables: BBC Sport, Wikipedia season pages, J.League official standings; Japanese Saturday records "
        "restored to pre-match by subtracting the 17 Oct result). Small early-season samples make these "
        "probabilities rough, not exact.", small)]

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=9 * mm,
                            title="Match-total goal picks 17-18 Oct 2026", author="football-analysis")
    doc.build(story)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--input", type=Path, default=INPUT)
    args = ap.parse_args(argv)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    rows = analyse_matches(data)
    over, below = select(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, over, below, args.out / "match_total_goal_picks.csv")
    if not args.no_pdf:
        write_pdf(rows, over, below, args.out / "match_total_goal_picks_2026-10-17.pdf")
    print(f"Matches evaluated: {len(rows)}  OVER (total 2+): {len(over)}  BELOW (total <=3): {len(below)}")
    for r in sorted(rows, key=lambda r: -max(r["p_ge_2"], r["p_le_3"])):
        tag = "OVER " if r in over else "BELOW" if r in below else "  -  "
        print(f" {tag} xGtot {r['lambda_total']:.2f}  P2+ {r['p_ge_2'] * 100:5.1f}%  "
              f"P3+ {r['p_ge_3'] * 100:5.1f}%  P<=3 {r['p_le_3'] * 100:5.1f}%  {r['match']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
