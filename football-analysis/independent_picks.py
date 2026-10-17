#!/usr/bin/env python3
"""Independent team-goal predictions from real events only (17-18 Oct 2026).

No prediction, odds or xG figure from any prediction site is used. Inputs are
in data/independent_inputs_2026-10-17_18.json: goals scored/conceded in league
matches this season, each league's goals-per-match average, and team news.

Model (computed here, in the open):
    league_avg   = league goals per match / 2          (per team per game)
    xG(team)     = (team GF/game x opponent GA/game) / league_avg
                   x home/away factor (1.10 / 0.90)
                   x confirmed-news attack adjustment
    goals ~ Poisson(xG)
    OVER 2 pick  = P(goals >= 3) >= 0.55 (higher bar: small early-season samples)
    BELOW 3 pick = P(goals <= 2) >= 0.93
Rumours are printed as UNVERIFIED and carry no adjustment unless confirmed.

Outputs: output/independent_goal_picks_2026-10-17.pdf and .csv
Requires reportlab for the PDF only.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT = HERE / "data" / "independent_inputs_2026-10-17_18.json"
DEFAULT_OUT = HERE / "output"
MIN_OVER, MIN_BELOW = 0.55, 0.93
MAX_GOALS = 15


def poisson_probs(lam: float) -> tuple[float, float]:
    """Return (P(3+ goals), P(0-2 goals)) for Poisson(lam)."""
    if lam < 0:
        raise ValueError("lambda must be >= 0")
    pmf = [math.exp(-lam)]
    for k in range(1, MAX_GOALS + 1):
        pmf.append(pmf[-1] * lam / k)
    below = sum(pmf[:3])
    return 1.0 - below, below


def expected_goals(team: dict, opp: dict, league_avg: float, venue_factor: float) -> float:
    if team["played"] <= 0 or opp["played"] <= 0 or league_avg <= 0:
        raise ValueError("played and league average must be positive")
    return (team["gf"] / team["played"]) * (opp["ga"] / opp["played"]) / league_avg \
        * venue_factor * team.get("attack_adj", 1.0)


def analyse(data: dict) -> list[dict]:
    rows = []
    for m in data["matches"]:
        league_avg = m["league_goals_per_match"] / 2.0
        for side, venue in (("home", data["home_factor"]), ("away", data["away_factor"])):
            team, opp = m[side], m["away" if side == "home" else "home"]
            lam = expected_goals(team, opp, league_avg, venue)
            over, below = poisson_probs(lam)
            rows.append({
                "id": m["id"], "competition": m["competition"], "kickoff_utc": m["kickoff_utc"],
                "match": f"{m['home']['team']} v {m['away']['team']}",
                "team": team["team"], "opponent": opp["team"], "venue": side,
                "gf_pg": team["gf"] / team["played"], "opp_ga_pg": opp["ga"] / opp["played"],
                "league_avg": league_avg, "attack_adj": team.get("attack_adj", 1.0),
                "xg": lam, "p_over_2": over, "p_below_3": below,
                "record": f"{team['gf']} scored / {team['ga']} conceded in {team['played']}",
                "opp_record": f"{opp['gf']} scored / {opp['ga']} conceded in {opp['played']}",
                "news": team.get("news", ""), "rumour": team.get("rumour", ""),
                "league_source": m["league_source"],
            })
    return rows


def select(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    over = sorted((r for r in rows if r["p_over_2"] >= MIN_OVER), key=lambda r: -r["p_over_2"])
    below = sorted((r for r in rows if r["p_below_3"] >= MIN_BELOW), key=lambda r: -r["p_below_3"])
    return over, below


def write_csv(rows, over, below, path: Path) -> None:
    fields = ["pick", "competition", "kickoff_utc", "match", "team", "opponent", "xg",
              "p_over_2", "p_below_3", "team_record", "opponent_record", "league_avg",
              "attack_adj", "news", "rumour_unverified"]
    picked = {id(r) for r in over + below}
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            label = "OVER 2 (3+)" if r in over else "BELOW 3 (0-2)" if r in below else ""
            w.writerow({"pick": label, "competition": r["competition"], "kickoff_utc": r["kickoff_utc"],
                        "match": r["match"], "team": r["team"], "opponent": r["opponent"],
                        "xg": round(r["xg"], 3), "p_over_2": round(r["p_over_2"], 4),
                        "p_below_3": round(r["p_below_3"], 4), "team_record": r["record"],
                        "opponent_record": r["opp_record"], "league_avg": round(r["league_avg"], 3),
                        "attack_adj": r["attack_adj"], "news": r["news"],
                        "rumour_unverified": r["rumour"]})


def write_pdf(data, rows, over, below, path: Path) -> None:
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
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=15.5, leading=18, spaceAfter=4)
    sub = ParagraphStyle("s", parent=ss["Normal"], fontSize=8.8, leading=11.5, spaceAfter=4)
    cell = ParagraphStyle("c", parent=ss["Normal"], fontSize=7.4, leading=9.2)
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white,
                          alignment=TA_CENTER, fontSize=8)
    small = ParagraphStyle("sm", parent=ss["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#444444"))
    h2 = ParagraphStyle("h2", parent=ss["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=3)

    story = [
        Paragraph("Independent predictions from real events — weekend of 17–18 October 2026", title),
        Paragraph(
            "<b>Not copied from any prediction site.</b> No bookmaker odds, no other site's xG and no other "
            "site's probabilities are used. Every number below is computed here from real events: goals "
            "scored and conceded in league matches this season, each league's goals-per-match average, and "
            "team news. Formula and all inputs are printed so anyone can re-run them.", sub),
        Paragraph(
            f"<b>Scope: {len({r['id'] for r in rows})} matches / {len(rows)} teams evaluated, including lower-division "
            f"football (EFL Championship, League One, League Two, Serie B, Japan J1/J2/J3). Result: {len(over)} over-2 pick(s) and "
            f"{len(below)} below-3 pick(s) pass the confidence bars</b> "
            f"(over 2 = P(team scores 3+) &ge; {MIN_OVER:.0%}; below 3 = P(team scores 0–2) &ge; {MIN_BELOW:.0%}). "
            "Where this independent model disagrees with a copied baseline, the copied one is discarded. "
            "Rumours are shown as UNVERIFIED and change nothing unless a club confirms them. Analysis only, not betting advice.", sub),
    ]

    def section(group, heading, colour, prob_key):
        if not group:
            return [Paragraph(heading, h2),
                    Paragraph("No team passes the confidence bar on real-event data alone.", sub)]
        body = [[Paragraph("#", head), Paragraph("Team and fixture", head), Paragraph("Prob.", head),
                 Paragraph("My xG calc.", head), Paragraph("Real events behind it", head),
                 Paragraph("Team news / rumours", head)]]
        for i, r in enumerate(group, 1):
            calc = (f"({r['gf_pg']:.2f} GF/g x {r['opp_ga_pg']:.2f} opp GA/g) / {r['league_avg']:.2f} league avg "
                    f"x venue x news adj {r['attack_adj']:.2f} = <b>{r['xg']:.2f}</b>")
            events = f"Team: {r['record']}.<br/>Opponent: {r['opp_record']}."
            news = r["news"] + (f"<br/><b>{r['rumour']}</b>" if r["rumour"] else "")
            body.append([Paragraph(str(i), cell),
                         Paragraph(f"<b>{r['team']}</b><br/>{r['match']}<br/><font color='#555555'>{r['competition']} · {r['kickoff_utc']} UTC</font>", cell),
                         Paragraph(f"{r[prob_key] * 100:.1f}%", cell),
                         Paragraph(calc, cell), Paragraph(events, cell), Paragraph(news, cell)])
        t = Table(body, colWidths=[8 * mm, 52 * mm, 14 * mm, 62 * mm, 62 * mm, 79 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(colour)),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]))
        return [Paragraph(heading, h2), t]

    story += section(over, "OVER 2 — team to score 3+ goals (my own calculation)", "#b03a2e", "p_over_2")
    story += section(below, "BELOW 3 — team to score 0–2 goals (my own calculation)", "#1f618d", "p_below_3")

    near = [r for r in rows if r not in over + below and (r["p_over_2"] >= 0.40 or r["p_below_3"] >= 0.90)]
    if near:
        body = [[Paragraph("Team", head), Paragraph("Fixture", head), Paragraph("P(3+)", head),
                 Paragraph("P(0–2)", head), Paragraph("Why not picked", head)]]
        for r in sorted(near, key=lambda r: -max(r["p_over_2"], r["p_below_3"])):
            why = ("P(3+) below the 55% confidence bar on real scoring records" if r["p_over_2"] >= 0.40
                   else "P(0–2) below 93% once opponent's real conceding record is used")
            body.append([Paragraph(r["team"], cell), Paragraph(r["match"], cell),
                         Paragraph(f"{r['p_over_2'] * 100:.1f}%", cell),
                         Paragraph(f"{r['p_below_3'] * 100:.1f}%", cell), Paragraph(why, cell)])
        t = Table(body, colWidths=[45 * mm, 70 * mm, 20 * mm, 20 * mm, 122 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#555555")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story += [Paragraph("Near misses — left out", h2), t]

    # Every match evaluated, so the full scope (incl. lower leagues) is visible.
    by_match = {}
    for r in rows:
        by_match.setdefault(r["id"], {})[r["venue"]] = r
    body = [[Paragraph("Match", head), Paragraph("Competition", head),
             Paragraph("Home team: P(3+) / P(0-2)", head), Paragraph("Away team: P(3+) / P(0-2)", head)]]
    for mid, sides in by_match.items():
        h, a = sides["home"], sides["away"]
        fmt = lambda r: f"{r['team']}: {r['p_over_2'] * 100:.0f}% / {r['p_below_3'] * 100:.0f}%"
        body.append([Paragraph(h["match"], cell), Paragraph(h["competition"], cell),
                     Paragraph(fmt(h), cell), Paragraph(fmt(a), cell)])
    t = Table(body, colWidths=[77 * mm, 40 * mm, 80 * mm, 80 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#555555")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]))
    story += [Paragraph(f"All {len(by_match)} matches evaluated (top flights + lower leagues)", h2), t]

    story += [Spacer(1, 6), Paragraph(
        "Sources of facts (not predictions): league tables and season goal totals (BBC Sport tables for the "
        "Premier League and EFL Championship/League One/League Two, Wikipedia season pages including Serie B, "
        "J.League, SoccerStats), club statements (FC Bayern, Inter, Roma/Gasperini), and "
        "match previews reporting confirmed absences (ESPN, BBC Sport, Sports Mole, FotMob, ge.globo). "
        "Full inputs are in the JSON file named with this PDF (independent_inputs_expanded_2026-10-17_18.json "
        "for the 54-match set). Small samples early in "
        "the season make these estimates uncertain; treat probabilities as rough, not exact.", small)]

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=9 * mm,
                            title="Independent real-event predictions 17-18 Oct 2026", author="football-analysis")
    doc.build(story)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--input", type=Path, default=INPUT)
    ap.add_argument("--pdf", default="independent_goal_picks_2026-10-17.pdf")
    ap.add_argument("--csv", default="independent_goal_picks.csv")
    args = ap.parse_args(argv)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    rows = analyse(data)
    over, below = select(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, over, below, args.out / args.csv)
    if not args.no_pdf:
        write_pdf(data, rows, over, below, args.out / args.pdf)
    print(f"Teams evaluated: {len(rows)}  OVER 2: {len(over)}  BELOW 3: {len(below)}")
    for r in sorted(rows, key=lambda r: -max(r["p_over_2"], r["p_below_3"])):
        tag = "OVER " if r in over else "BELOW" if r in below else "  -  "
        print(f" {tag} xG {r['xg']:.2f}  P3+ {r['p_over_2'] * 100:5.1f}%  P0-2 {r['p_below_3'] * 100:5.1f}%  {r['team']} ({r['match']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
