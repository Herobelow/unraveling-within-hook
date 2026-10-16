#!/usr/bin/env python3
"""Football match outcome probabilities from market/model baselines plus news factors.

Pipeline for each match
-----------------------
1. Baseline 1X2 probabilities (home / draw / away) from a published source
   (MatchSharp market-implied odds, or Opta where no market value is available).
2. Factor adjustment: each news factor is a strength shift for one team,
   scaled by a confidence weight. The net shift s (home minus away, in
   log-odds units) moves the home/away ratio:
       p_home' ~ p_home * exp(s/2),  p_away' ~ p_away * exp(-s/2),  p_draw unchanged
   then the three values are renormalised.
3. Goal model: independent Poisson home/away goal counts are fitted so that
   their 1X2 probabilities match the adjusted values. From the fitted rates we
   derive expected goals, P(Over 2.5), P(both teams score) and the most likely
   scores.

Standard library only. Run:  python3 predict.py
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE / "data" / "weekend_2026-10-17_18.json"
DEFAULT_OUT = HERE / "output"

MAX_GOALS = 12  # truncation for Poisson sums (tail mass is negligible at these rates)


# --------------------------------------------------------------------------- #
# Basic probability helpers
# --------------------------------------------------------------------------- #
def normalise(h: float, d: float, a: float) -> tuple[float, float, float]:
    total = h + d + a
    if total <= 0:
        raise ValueError("probabilities must sum to a positive value")
    return h / total, d / total, a / total


def factor_shift(factors: list[dict]) -> float:
    """Net shift in favour of the HOME side (log-odds units).

    A factor's `effect` is the strength change for `team` at full confidence:
    negative means that team is weakened. Its contribution is effect * confidence.
    A weakened home side lowers the shift; a weakened away side raises it.
    """
    shift = 0.0
    for f in factors:
        contribution = float(f["effect"]) * float(f.get("confidence", 1.0))
        if f["team"] == "home":
            shift += contribution
        elif f["team"] == "away":
            shift -= contribution
        else:
            raise ValueError(f"factor team must be 'home' or 'away', got {f['team']!r}")
    return shift


def apply_shift(h: float, d: float, a: float, shift: float) -> tuple[float, float, float]:
    return normalise(h * math.exp(shift / 2.0), d, a * math.exp(-shift / 2.0))


# --------------------------------------------------------------------------- #
# Poisson goal model
# --------------------------------------------------------------------------- #
def poisson_pmf(lam: float, n: int = MAX_GOALS) -> list[float]:
    probs = [math.exp(-lam)]
    for k in range(1, n + 1):
        probs.append(probs[-1] * lam / k)
    return probs


def outcome_probs(lh: float, la: float) -> tuple[float, float, float]:
    ph, pa = poisson_pmf(lh), poisson_pmf(la)
    home = draw = away = 0.0
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            p = x * y
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    return home, draw, away


def fit_poisson(h: float, d: float, a: float) -> tuple[float, float]:
    """Find expected goals (lambda_home, lambda_away) whose Poisson 1X2 matches (h, d, a).

    Coarse grid search followed by three refinement passes. Squared error is
    sufficient here because the mapping is smooth and well behaved.
    """

    def err(lh: float, la: float) -> float:
        H, D, A = outcome_probs(lh, la)
        return (H - h) ** 2 + (D - d) ** 2 + (A - a) ** 2

    grid = [round(0.2 + 0.1 * i, 3) for i in range(40)]  # 0.2 .. 4.1
    best = min(((err(lh, la), lh, la) for lh in grid for la in grid))
    _, lh, la = best
    step = 0.1
    for _ in range(3):
        cands = [
            (err(lh + i * step / 10, la + j * step / 10), lh + i * step / 10, la + j * step / 10)
            for i in range(-10, 11)
            for j in range(-10, 11)
        ]
        _, lh, la = min(cands)
        lh, la = max(lh, 0.01), max(la, 0.01)
        step /= 10
    return lh, la


def score_summary(lh: float, la: float) -> dict:
    ph, pa = poisson_pmf(lh), poisson_pmf(la)
    matrix = {(i, j): ph[i] * pa[j] for i in range(MAX_GOALS + 1) for j in range(MAX_GOALS + 1)}
    under25 = sum(p for (i, j), p in matrix.items() if i + j <= 2)
    btts = (1 - ph[0]) * (1 - pa[0])
    top = sorted(matrix.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return {
        "p_over_2_5": 1 - under25,
        "p_btts": btts,
        "top_scores": [(f"{i}-{j}", p) for (i, j), p in top],
    }


# --------------------------------------------------------------------------- #
# Match-level analysis
# --------------------------------------------------------------------------- #
def grade(match: dict) -> str:
    """Confidence label from source agreement. Factors are reported separately."""
    base, sec = match["baseline"], match.get("secondary")
    if not sec:
        return "Medium (single source)"
    diff = max(abs(base["home"] - sec["home"]), abs(base["away"] - sec["away"]))
    if diff <= 0.05:
        return "High (sources agree within 5 pts)"
    if diff <= 0.10:
        return "Medium (sources differ by 5-10 pts)"
    return "Low (sources differ by more than 10 pts)"


def analyse(match: dict) -> dict:
    base = match["baseline"]
    b_h, b_d, b_a = normalise(base["home"], base["draw"], base["away"])
    shift = factor_shift(match.get("factors", []))
    h, d, a = apply_shift(b_h, b_d, b_a, shift)
    lh, la = fit_poisson(h, d, a)
    goals = score_summary(lh, la)
    return {
        "id": match["id"],
        "competition": match["competition"],
        "window": match["window"],
        "home": match["home"],
        "away": match["away"],
        "baseline_source": base["source"],
        "baseline": (b_h, b_d, b_a),
        "secondary": match.get("secondary"),
        "net_shift": shift,
        "adjusted": (h, d, a),
        "xg_home": lh,
        "xg_away": la,
        "p_over_2_5": goals["p_over_2_5"],
        "p_btts": goals["p_btts"],
        "top_scores": goals["top_scores"],
        "grade": grade(match),
        "factors": match.get("factors", []),
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "competition", "window", "home", "away", "baseline_source",
        "base_home", "base_draw", "base_away", "net_shift",
        "adj_home", "adj_draw", "adj_away", "xg_home", "xg_away",
        "p_over_2_5", "p_btts", "most_likely_score", "grade",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "competition": r["competition"], "window": r["window"],
                "home": r["home"], "away": r["away"], "baseline_source": r["baseline_source"],
                "base_home": round(r["baseline"][0], 4), "base_draw": round(r["baseline"][1], 4),
                "base_away": round(r["baseline"][2], 4), "net_shift": round(r["net_shift"], 4),
                "adj_home": round(r["adjusted"][0], 4), "adj_draw": round(r["adjusted"][1], 4),
                "adj_away": round(r["adjusted"][2], 4),
                "xg_home": round(r["xg_home"], 2), "xg_away": round(r["xg_away"], 2),
                "p_over_2_5": round(r["p_over_2_5"], 4), "p_btts": round(r["p_btts"], 4),
                "most_likely_score": r["top_scores"][0][0], "grade": r["grade"],
            })


def write_report(data: dict, rows: list[dict], path: Path) -> None:
    out: list[str] = []
    out.append("# Football outcome probabilities: weekend of 17-18 October 2026\n")
    out.append(f"As of {data['as_of']} (UTC). Generated by `football-analysis/predict.py`.\n")
    out.append(f"**Scope:** {data['scope']}\n")
    out.append(
        "**Method:** baseline 1X2 probabilities (MatchSharp market-implied where available, "
        "otherwise Opta) are shifted by news factors (`effect x confidence`, log-odds units). "
        "A Poisson goal model is then fitted to the adjusted 1X2 to give expected goals, "
        "Over 2.5 and BTTS. Probabilities are estimates, not guarantees, and this is not betting advice.\n"
    )
    out.append(
        "**Caveats:** (1) Market baselines already include widely known team news, so factor "
        "adjustments only add information the market may not yet price. Treat them as a "
        "judgement overlay. (2) Factor sizes are analyst judgement, not fitted to historical data. "
        "(3) Opta-only matches may already include rest effects, so some congestion adjustments "
        "there risk double counting. (4) Independent Poisson ignores the low-score correlation "
        "that Dixon-Coles corrects, so draw probabilities may be slightly understated.\n"
    )

    competitions = []
    for r in rows:
        if r["competition"] not in competitions:
            competitions.append(r["competition"])

    for comp in competitions:
        out.append(f"\n## {comp}\n")
        out.append(
            "| Window | Match | Baseline H / D / A (source) | Adjusted H / D / A | Net shift | xG (H-A) | Over 2.5 | BTTS | Likely score | Confidence |"
        )
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            if r["competition"] != comp:
                continue
            b, a_ = r["baseline"], r["adjusted"]
            out.append(
                f"| {r['window']} | **{r['home']} v {r['away']}** | "
                f"{pct(b[0])} / {pct(b[1])} / {pct(b[2])} ({r['baseline_source']}) | "
                f"{pct(a_[0])} / {pct(a_[1])} / {pct(a_[2])} | {r['net_shift']:+.3f} | "
                f"{r['xg_home']:.2f} - {r['xg_away']:.2f} | {pct(r['p_over_2_5'])} | {pct(r['p_btts'])} | "
                f"{r['top_scores'][0][0]} ({pct(r['top_scores'][0][1])}) | {r['grade']} |"
            )

    out.append("\n## Source cross-check (where a second source exists)\n")
    out.append("| Match | MatchSharp H / A | Opta H / A | Opta draw (derived) |")
    out.append("|---|---|---|---|")
    for r in rows:
        sec = r["secondary"]
        if not sec:
            continue
        sec_draw = 1 - sec["home"] - sec["away"]
        if r["baseline_source"] == "matchsharp":
            ms = f"{pct(r['baseline'][0])} / {pct(r['baseline'][2])}"
        else:
            ms = "n/a (baseline is Opta)"
        out.append(f"| {r['home']} v {r['away']} | {ms} | {pct(sec['home'])} / {pct(sec['away'])} | {pct(sec_draw)} |")

    out.append("\n## Factor log\n")
    out.append("Effect is the strength change for the named team at full confidence (negative = weaker). Net shift is home minus away.\n")
    out.append("| Match | Team | Factor | Effect | Confidence | Source |")
    out.append("|---|---|---|---|---|---|")
    any_factor = False
    for r in rows:
        for f in r["factors"]:
            any_factor = True
            out.append(
                f"| {r['home']} v {r['away']} | {f['team']} | {f['label']} | {f['effect']:+.2f} | "
                f"{f['confidence']:.1f} | {f['source']} |"
            )
    if not any_factor:
        out.append("| - | - | no factors | - | - | - |")

    out.append("\n## News and rumour log (with reliability tier)\n")
    out.append("| Date | Item | Tier | Source |")
    out.append("|---|---|---|---|")
    for n in data.get("news_log", []):
        out.append(f"| {n['date']} | {n['item']} | {n['tier']} | {n['source']} |")

    out.append("\n## Sources\n")
    for key, s in data["sources"].items():
        out.append(f"- **{key}**: [{s['name']}]({s['url']})")
    out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    data = json.loads(args.data.read_text(encoding="utf-8"))
    rows = [analyse(m) for m in data["matches"]]

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.out / "predictions.csv")
    write_report(data, rows, args.out / "report.md")

    print(f"{'Match':38s} {'Base H/D/A':22s} {'Adj H/D/A':22s} {'xG':11s} {'O2.5':>6s} {'BTTS':>6s}")
    for r in rows:
        b, a_ = r["baseline"], r["adjusted"]
        name = f"{r['home']} v {r['away']}"[:38]
        print(
            f"{name:38s} {pct(b[0]):>7s}/{pct(b[1]):>6s}/{pct(b[2]):>6s} "
            f"{pct(a_[0]):>7s}/{pct(a_[1]):>6s}/{pct(a_[2]):>6s} "
            f"{r['xg_home']:.2f}-{r['xg_away']:.2f} {pct(r['p_over_2_5']):>6s} {pct(r['p_btts']):>6s}"
        )
    print(f"\nWrote {args.out / 'report.md'} and {args.out / 'predictions.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
