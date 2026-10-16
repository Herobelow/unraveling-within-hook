#!/usr/bin/env python3
"""Clean, verified-only team goal picks for 17-18 October 2026.

Reads data/verified_picks_2026-10-17_18.json, which lists only the picks that
passed the fixture and team-news checks (see the "method" field in that file).
For each pick it looks up the goal-model probability from team_goal_picks.py
and refuses to build the sheet if a pick is missing, mis-matched, or below
its threshold.

Outputs (in output/):
    verified_goal_picks_2026-10-17.pdf   clean sheet: picks plus exclusions
    verified_goal_picks.csv              the verified picks with probabilities

Requires reportlab for the PDF (pip install reportlab). The checks are stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import team_goal_picks as tgp

HERE = Path(__file__).resolve().parent
VERIFIED_FILE = HERE / "data" / "verified_picks_2026-10-17_18.json"
DEFAULT_OUT = HERE / "output"

MIN_OVER = 0.50   # team 3+ goals
MIN_BELOW = 0.93  # team 0-2 goals


def load_verified(path: Path = VERIFIED_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def attach_probabilities(verified: dict, rows: list[dict]) -> list[dict]:
    """Return the picks with the model probability filled in.

    Raises ValueError if a pick is not found, if the team is not in the fixture,
    or if its probability is below the threshold for its side.
    """
    by_key = {(r["match_id"], r["team"]): r for r in rows}
    out = []
    for pick in verified["picks"]:
        key = (pick["match_id"], pick["team"])
        if key not in by_key:
            raise ValueError(f"pick not found in the model data: {pick['team']} ({pick['match_id']})")
        r = by_key[key]
        if pick["side"] == "over2":
            prob = r["p_over_2"]
            if prob < MIN_OVER:
                raise ValueError(f"{pick['team']} over 2 is {prob:.3f}, below {MIN_OVER}")
            label = "OVER 2 (team 3+ goals)"
        elif pick["side"] == "below3":
            prob = r["p_below_3"]
            if prob < MIN_BELOW:
                raise ValueError(f"{pick['team']} below 3 is {prob:.3f}, below {MIN_BELOW}")
            label = "BELOW 3 (team 0-2 goals)"
        else:
            raise ValueError(f"unknown side {pick['side']!r} for {pick['team']}")
        out.append({
            **pick,
            "label": label,
            "probability": prob,
            "xg": r["xg"],
            "match": r["match"],
            "competition": r["competition"],
            "window": r["window"],
        })
    ids = [p["match_id"] for p in verified["picks"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate match_id in the verified list")
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def write_csv(picks: list[dict], path: Path) -> None:
    fields = ["side", "competition", "window", "match", "team", "kickoff_utc",
              "probability", "xg", "news", "sources"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for p in picks:
            w.writerow({
                "side": p["label"], "competition": p["competition"], "window": p["window"],
                "match": p["match"], "team": p["team"], "kickoff_utc": p["kickoff_utc"],
                "probability": round(p["probability"], 4), "xg": round(p["xg"], 3),
                "news": p["news"], "sources": p["sources"],
            })


def write_pdf(verified: dict, picks: list[dict], path: Path) -> None:
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
    sub = ParagraphStyle("s", parent=styles["Normal"], fontSize=8.8, leading=11.5, spaceAfter=4)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7.6, leading=9.4)
    head = ParagraphStyle("h", parent=cell, fontName="Helvetica-Bold", textColor=colors.white,
                          alignment=TA_CENTER, fontSize=8.2)
    small = ParagraphStyle("sm", parent=styles["Normal"], fontSize=7, leading=9,
                           textColor=colors.HexColor("#444444"))
    h2 = ParagraphStyle("h2", parent=styles["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=3)

    over = [p for p in picks if p["side"] == "over2"]
    below = [p for p in picks if p["side"] == "below3"]

    story = [
        Paragraph("Verified team goal picks: weekend of Saturday 17 and Sunday 18 October 2026", title),
        Paragraph(
            f"Only picks that passed the checks are listed. <b>{len(picks)} picks</b> in total: "
            f"<b>{len(over)}</b> over-2 (team scores 3 or more) and <b>{len(below)}</b> below-3 (team scores "
            "0, 1 or 2). Checks: fixture and kick-off confirmed, team news checked in at least two "
            "sources, and the model probability at or above the threshold. Doubtful matches were removed. "
            "The requested date 17/10/2025 is already past, so this sheet covers 17/10/2026.",
            sub),
        Paragraph(
            "<b>Caveats:</b> the probabilities come from a Poisson goal model fed by Sports4Cast and "
            "MatchSharp/Opta baselines. Sports4Cast's own accuracy record could not be verified, so these are "
            "estimates, not proof. Only one over-2 pick passed the checks. No rumours are included; any "
            "unconfirmed report would be labelled unverified. This is analysis, not betting advice.",
            sub),
    ]

    def table_for(group: list[dict], heading: str, colour: str) -> list:
        rows = [[Paragraph("#", head), Paragraph("Team and fixture", head), Paragraph("Prob.", head),
                 Paragraph("Kick-off (UTC)", head), Paragraph("Team news (verified)", head),
                 Paragraph("Sources", head)]]
        for i, p in enumerate(group, 1):
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(f"<b>{p['team']}</b><br/>{p['match']}<br/>"
                          f"<font color='#555555'>{p['competition']} · {p['window']}</font>", cell),
                Paragraph(f"{p['probability'] * 100:.1f}%", cell),
                Paragraph(p["kickoff_utc"], cell),
                Paragraph(p["news"], cell),
                Paragraph(p["sources"], small),
            ])
        t = Table(rows, colWidths=[9 * mm, 58 * mm, 15 * mm, 25 * mm, 110 * mm, 60 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(colour)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ]))
        return [Paragraph(heading.replace("<br/>", " "), h2), t]

    if over:
        story += table_for(over, "OVER 2: team to score 3+ goals", "#b03a2e")
    if below:
        story += table_for(below, "BELOW 3: team to score 0-2 goals", "#1f618d")

    excluded = verified.get("excluded", [])
    if excluded:
        rows = [[Paragraph("Match", head), Paragraph("Pick considered", head),
                 Paragraph("Why it was left out", head)]]
        for e in excluded:
            rows.append([Paragraph(e["match"], cell), Paragraph(e["pick"], cell), Paragraph(e["reason"], cell)])
        et = Table(rows, colWidths=[62 * mm, 50 * mm, 165 * mm], repeatRows=1)
        et.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#555555")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f7f7f7"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbbb")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story += [Paragraph("Considered and left out", h2), et]

    story += [
        Spacer(1, 6),
        Paragraph(
            "Method: expected goals per team from each match's 1X2 probabilities. Full-time goals are modelled "
            "as independent Poisson distributions. Rumours are labelled as unverified. Kick-off times are UTC "
            "as reported by sources; check your local time. Full data and the verification notes are in "
            "football-analysis/data/verified_picks_2026-10-17_18.json.",
            small),
    ]

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=9 * mm, bottomMargin=9 * mm,
                            title="Verified team goal picks 17-18 Oct 2026", author="football-analysis")
    doc.build(story)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args(argv)

    verified = load_verified()
    analysed, _ = tgp.load_analysed()
    rows = tgp.team_rows(analysed)
    picks = attach_probabilities(verified, rows)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(picks, args.out / "verified_goal_picks.csv")
    if not args.no_pdf:
        write_pdf(verified, picks, args.out / "verified_goal_picks_2026-10-17.pdf")

    print(f"Verified picks: {len(picks)}  (over 2: {sum(p['side'] == 'over2' for p in picks)}, "
          f"below 3: {sum(p['side'] == 'below3' for p in picks)})")
    for p in picks:
        print(f"  {p['probability'] * 100:5.1f}%  {p['label']:24s} {p['team']:20s} {p['match']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
