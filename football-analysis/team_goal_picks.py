#!/usr/bin/env python3
"""Team goal-band picks for the weekend of 17-18 October 2026.

For every team in every match, the goal model gives a full-time goal
distribution (independent Poisson with the expected goals fitted in predict.py).
From it:

    P(team scores over 2)  = P(3 or more goals)  -> "OVER 2" side
    P(team scores below 3) = P(0, 1 or 2 goals)  -> "BELOW 3" side

Selection rule ("leave out if in doubt"):
    * OVER side: only teams with P(3+) >= --min-over (default 0.50).
    * BELOW side: the most certain teams, ranked by P(0-2), down to --min-below
      (default 0.93), taking at most --n-below picks.
    * Total picks are capped at --total (default 50).

Outputs (in output/):
    team_goal_picks_2026-10-17.pdf   two-column PDF: OVER 2 side | BELOW 3 side
    team_goal_picks.csv              the picks
    team_goal_probabilities.csv      every team, both probabilities

Requires reportlab only for the PDF step (pip install reportlab). The model
itself is standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import predict as p

HERE = Path(__file__).resolve().parent
DATA_FILES = [
    HERE / "data" / "weekend_2026-10-17_18.json",       # top-5 leagues + Opta-only matches
    HERE / "data" / "other_leagues_2026-10-17_18.json",  # other leagues (Sports4Cast)
]
DEFAULT_OUT = HERE / "output"


# --------------------------------------------------------------------------- #
# Team-level probabilities
# --------------------------------------------------------------------------- #
def team_goal_probs(lam: float) -> tuple[float, float]:
    """Return (P(3+ goals), P(0-2 goals)) for a team with expected goals `lam`."""
    pmf = p.poisson_pmf(lam)
    below_3 = sum(pmf[:3])
    return 1.0 - below_3, below_3


def team_rows(analysed: list[dict]) -> list[dict]:
    rows = []
    for m in analysed:
        for side, team, opp, lam in (
            ("home", m["home"], m["away"], m["xg_home"]),
            ("away", m["away"], m["home"], m["xg_away"]),
        ):
            over, below = team_goal_probs(lam)
            rows.append({
                "match_id": m.get("id", ""),
                "competition": m["competition"],
                "window": m["window"],
                "match": f"{m['home']} v {m['away']}",
                "team": team,
                "side": side,
                "opponent": opp,
                "xg": lam,
                "p_over_2": over,
                "p_below_3": below,
                "baseline_source": m["baseline_source"],
                "grade": m["grade"],
            })
    return rows


def select_picks(rows: list[dict], min_over: float = 0.50, min_below: float = 0.93,
                 n_below: int = 45, total: int = 50) -> tuple[list[dict], list[dict]]:
    """Return (over_picks, below_picks) following the 'leave out if in doubt' rule."""
    over_pool = sorted((r for r in rows if r["p_over_2"] >= min_over),
                       key=lambda r: r["p_over_2"], reverse=True)
    below_pool = sorted((r for r in rows if r["p_below_3"] >= min_below),
                        key=lambda r: r["p_below_3"], reverse=True)

    n_below = min(n_below, total - min(len(over_pool), total))
    over = over_pool[: total - n_below]
    below = below_pool[:n_below]
    return over, below


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_analysed(files: list[Path] = DATA_FILES) -> tuple[list[dict], dict]:
    analysed: list[dict] = []
    sources: dict = {}
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for m in data["matches"]:
            analysed.append({**p.analyse(m), "id": m["id"]})
        sources.update(data.get("sources", {}))
    return analysed, sources


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def write_csvs(rows: list[dict], over: list[dict], below: list[dict], out: Path) -> None:
    fields = ["side_of_pick", "competition", "window", "match", "team", "opponent",
              "xg", "p_over_2", "p_below_3", "baseline_source", "grade"]

    def dump(path: Path, items: list[tuple[str, dict]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for label, r in items:
                w.writerow({
                    "side_of_pick": label, "competition": r["competition"], "window": r["window"],
                    "match": r["match"], "team": r["team"], "opponent": r["opponent"],
                    "xg": round(r["xg"], 3), "p_over_2": round(r["p_over_2"], 4),
                    "p_below_3": round(r["p_below_3"], 4),
                    "baseline_source": r["baseline_source"], "grade": r["grade"],
                })

    dump(out / "team_goal_picks.csv",
         [("OVER 2 (3+ goals)", r) for r in over] + [("BELOW 3 (0-2 goals)", r) for r in below])

    with (out / "team_goal_probabilities.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["competition", "window", "match", "team", "opponent", "xg",
                    "p_over_2", "p_below_3"])
        for r in sorted(rows, key=lambda r: (r["competition"], r["match"], r["team"])):
            w.writerow([r["competition"], r["window"], r["match"], r["team"], r["opponent"],
                        round(r["xg"], 3), round(r["p_over_2"], 4), round(r["p_below_3"], 4)])


def write_pdf(over: list[dict], below: list[dict], rows: list[dict], path: Path,
              min_over: float, min_below: float) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("reportlab is needed for the PDF: pip install reportlab") from exc

    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=16, leading=19, spaceAfter=4)
    sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=9, leading=12, spaceAfter=4)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7.6, leading=9.4)
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white,
                          alignment=TA_CENTER, fontSize=8.5)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.HexColor("#444444"))

    def entry(r: dict, prob: float) -> str:
        return (f"<b>{r['team']}</b><br/>{r['match']}<br/>"
                f"<font color='#555555'>{r['competition']} · {r['window']} · xG {r['xg']:.2f}</font>")

    n = max(len(over), len(below))
    body = [[Paragraph("#", head),
             Paragraph(f"OVER 2 GOALS — team to score 3+ (full time)<br/>{len(over)} picks", head),
             Paragraph("Prob.", head),
             Paragraph("BELOW 3 GOALS — team to score 0-2 (full time)<br/>{} picks".format(len(below)), head),
             Paragraph("Prob.", head)]]
    for i in range(n):
        o = over[i] if i < len(over) else None
        b = below[i] if i < len(below) else None
        body.append([
            Paragraph(str(i + 1), cell),
            Paragraph(entry(o, o["p_over_2"]), cell) if o else "",
            Paragraph(f"{o['p_over_2'] * 100:.1f}%", cell) if o else "",
            Paragraph(entry(b, b["p_below_3"]), cell) if b else "",
            Paragraph(f"{b['p_below_3'] * 100:.1f}%", cell) if b else "",
        ])

    col_widths = [8 * mm, 108 * mm, 16 * mm, 108 * mm, 16 * mm]
    table = Table(body, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#333333")),
        ("BACKGROUND", (1, 0), (2, 0), colors.HexColor("#b03a2e")),
        ("BACKGROUND", (3, 0), (4, 0), colors.HexColor("#1f618d")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (1, 1), (2, -1), [colors.HexColor("#fdf2f0"), colors.white]),
        ("ROWBACKGROUNDS", (3, 1), (4, -1), [colors.HexColor("#eef5fb"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
    ]))

    exp_over = sum(o["p_over_2"] for o in over)
    exp_below = sum(b["p_below_3"] for b in below)
    total = len(over) + len(below)
    all_picks = over + below
    exp_all = exp_over + exp_below
    min_over_p = min((o["p_over_2"] for o in over), default=0)
    min_below_p = min((b["p_below_3"] for b in below), default=0)

    story = [
        Paragraph("Team goal picks — weekend of Saturday 17 and Sunday 18 October 2026", title),
        Paragraph(
            "Requested date was 17/10/2025. That date is already past (today is 16 Oct 2026) and the sources "
            "only hold upcoming fixtures, so this sheet covers the 17/10/2026 weekend. "
            f"Picks: <b>{total}</b> in total. Over-2 side: <b>{len(over)}</b> (each at least "
            f"{min_over_p * 100:.0f}%). Below-3 side: <b>{len(below)}</b> (each at least "
            f"{min_below_p * 100:.0f}%). Doubtful teams were left out.", sub),
        Paragraph(
            "<b>How to read it:</b> left column = teams the model expects to score 3 or more goals at full time; "
            "right column = teams expected to finish with 0, 1 or 2 goals. Probability is the model's chance the "
            "statement is true for that team's full-time goals. It is an estimate, not a guarantee.", sub),
        Spacer(1, 3),
        table,
        Spacer(1, 6),
        Paragraph(
            f"Expected hits if the model is right: about <b>{exp_all:.1f} of {total}</b> "
            f"(over side {exp_over:.1f} of {len(over)}; below side {exp_below:.1f} of {len(below)}). "
            "Treat these as upper-bound estimates: a Poisson model underweights blow-outs and surprise "
            "scorers, so real hit rates on the over side are likely lower than the figures shown.", sub),
        Paragraph(
            "<b>Why the over side has few picks:</b> no team in these leagues has more than a 64% chance of "
            "scoring 3 or more on this model. The next candidates are around 40-46% and were left out on "
            "purpose. The below-3 side is more reliable because most teams are unlikely to reach 3 goals.", sub),
        Paragraph(
            "<b>Method and sources:</b> expected goals from each match's 1X2 probabilities (Sports4Cast ML "
            "predictions for the other leagues; MatchSharp market-implied odds and Opta for the top five "
            "leagues, with news adjustments from the first report). Each team's full-time goals are "
            "modelled as independent Poisson. Full data, sources and factors are in football-analysis/. "
            "Not betting advice. Gamble only what you can afford to lose.", small),
    ]

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=10 * mm, bottomMargin=10 * mm,
                            title="Team goal picks 17-18 Oct 2026", author="football-analysis")
    doc.build(story)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min-over", type=float, default=0.50)
    ap.add_argument("--min-below", type=float, default=0.93)
    ap.add_argument("--n-below", type=int, default=45)
    ap.add_argument("--total", type=int, default=50)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-pdf", action="store_true", help="skip the PDF (CSV only)")
    args = ap.parse_args(argv)

    analysed, _ = load_analysed()
    rows = team_rows(analysed)
    over, below = select_picks(rows, args.min_over, args.min_below, args.n_below, args.total)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csvs(rows, over, below, args.out)
    if not args.no_pdf:
        write_pdf(over, below, rows, args.out / "team_goal_picks_2026-10-17.pdf", args.min_over, args.min_below)

    print(f"Matches analysed: {len(analysed)}  |  teams scored: {len(rows)}")
    print(f"OVER 2 picks: {len(over)}   BELOW 3 picks: {len(below)}   total: {len(over) + len(below)}")
    print("\nOVER 2 (3+ goals):")
    for r in over:
        print(f"  {r['p_over_2'] * 100:5.1f}%  {r['team']:28s} {r['match']}  ({r['competition']})")
    print("\nBELOW 3 (0-2 goals):")
    for r in below:
        print(f"  {r['p_below_3'] * 100:5.1f}%  {r['team']:28s} {r['match']}  ({r['competition']})")
    if not args.no_pdf:
        print(f"\nWrote {args.out / 'team_goal_picks_2026-10-17.pdf'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
