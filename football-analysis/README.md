# Football outcome analysis: weekend of 17-18 October 2026

Probability estimates for football matches (top five European leagues plus two
Opta-only fixtures), built from published market and model baselines and adjusted
for team news, injuries, fixture congestion and pressure stories.

- `data/weekend_2026-10-17_18.json`: fixtures, baseline probabilities, news factors with confidence weights, sources, and a dated news log with reliability tiers.
- `predict.py`: the model. Standard library only, no installs needed.
- `test_predict.py`: unit tests for the sign conventions, the probability maths, the Poisson fit and the dataset.
- `output/report.md`: generated report with all tables, the factor log, and the news log.
- `output/predictions.csv`: generated numbers in one flat file.

## Run

```bash
cd football-analysis
python3 predict.py              # regenerates output/
python3 -m unittest -v test_predict
```

To update the analysis, edit the JSON (add a match, change a factor, or add a
news item with its source), then re-run `predict.py`.

## Method

1. **Baseline.** Home / draw / away probabilities from MatchSharp (market-implied,
   margin removed). Where no market value was available, Opta's supercomputer
   probabilities were used (Man City v Ipswich and Coventry v Tottenham).
2. **News factors.** Each factor changes one team's strength by `effect x confidence`
   (log-odds units). The net shift `s` (home minus away) updates the home/away ratio:
   `p_home' ~ p_home * exp(s/2)`, `p_away' ~ p_away * exp(-s/2)`, draw unchanged,
   then renormalised.
3. **Goals.** Independent Poisson home and away goal counts are fitted so their 1X2
   matches the adjusted probabilities. This gives expected goals, P(Over 2.5),
   P(BTTS) and the most likely scores.
4. **Confidence grade.** Based on source agreement only: High if MatchSharp and Opta
   differ by 5 points or less on both home and away, Medium if 5-10 points or a single
   source, Low if more than 10 points.

### Factor sizes (judgement, not fitted to data)

| Factor | Effect on the affected team | Basis |
|---|---|---|
| Played European match within about 3 days, opponent did not | -0.06 | Congestion. Default assumption. |
| Striker ruled out (confirmed) | -0.08 | Key-player absence |
| Centre-back out (confirmed) | -0.05 | Depth is often available, so smaller |
| Midfield creator or defensive midfielder out | -0.04 | |
| Manager or club under reported pressure | -0.03 | Narrative, often already priced |
| Returning key player | +0.03 to +0.04 | Positive offset |

Confidence weights: confirmed or official = 1.0, credible report = 0.5-0.6,
single or low-credibility source = 0.3.

## Key takeaways (from `output/report.md`)

- **Strongest favourites:** Bayern v Leipzig (79% home, adjusted 79%), Real Madrid v Sevilla (76% after rest adjustment), Man City v Ipswich (72% per Opta, after a 3-day rest adjustment), Villarreal v Elche (66%) and Barcelona at Betis (70% after a Betis rest adjustment).
- **Most open contests:** Everton v Chelsea, Newcastle v Aston Villa and Leeds v Man Utd all sit near 30-45% for each side with draws around 26-27%.
- **Most news-sensitive match:** Leeds v Man Utd. The Sesko absence and pressure on the Man Utd manager move the home-win estimate from 41% to 43%. Sesko's absence is probably already in the market price, so treat this as a judgement overlay.
- **Biggest source disagreement (low confidence):** Everton v Chelsea. MatchSharp has Chelsea 43% and Everton 31%, while Opta has Everton 43% and Chelsea 30%. That is a swing of about 12 points on each side, so the Everton-favoured view comes from the model and the Chelsea-favoured view from the market. Fulham v Hull is also Low for the same reason (56% vs 45% for Fulham).
- **Goals:** Over 2.5 is most likely in Bayern v Leipzig (81%), Brighton v Palace (61%) and Real Betis v Barcelona (76%). Forest v Arsenal (36%) and Lorient v Monaco (37%) look lowest.

## Limitations (read before using)

- **Market baselines already contain public team news.** The adjustments only add information the market may not yet price. Treat them as a judgement overlay, not an edge.
- **Factor sizes are not calibrated.** They were set by hand and have not been backtested against past results. No historical dataset was used.
- **Double counting risk.** Opta's model may already include rest days. The Opta-only rows (Man City, Coventry) may therefore be over-adjusted.
- **Independent Poisson** ignores the low-score correlation that Dixon-Coles corrects. Draw probabilities may be slightly understated and 0-0 / 1-1 scores may be underweighted.
- **Staleness.** Team news is dated 12-16 Oct 2026. Lineups are not known; check official team sheets before kick-off.
- **News reliability.** One item (Man Utd surgery, Sesko) comes from a journalist report. The Roma midfielder Kone injury comes from a single low-credibility aggregator and carries weight 0.3. Liverpool's Gakpo, Isak and Szoboszlai status is unconfirmed for this game.
- **Coverage gaps.** Championship, League Two, Champions League matchday 3 (20-21 Oct) fixtures and African / Kenyan leagues are not modelled.
- **Not betting advice.** These are estimates. Probabilities for individual matches are often far from certain, and no model guarantees a result. If you bet, keep stakes you can afford to lose.

## Team goal picks (over 2 / below 3 goals), weekend 17-18 Oct 2026

Added later: a second model run that works per team, across 10 more leagues (Eredivisie,
Super Lig, Scottish Premiership, Greek Super League, Danish Superliga, Allsvenskan,
Brazilian Serie A, Argentinian Primera, J1 League, MLS) plus the top-five leagues.

- `data/other_leagues_2026-10-17_18.json`: 78 matches from Sports4Cast's 1X2 predictions (sources listed inside).
- `team_goal_picks.py`: for each team, P(3+ goals) = OVER 2 side, and P(0-2 goals) = BELOW 3 side. Selection: OVER side only at P >= 0.50; BELOW side from P >= 0.93, up to 45 picks; total capped at 50.
- `test_team_picks.py`: tests for the probability maths and the selection rules.
- Outputs: `output/team_goal_picks_2026-10-17.pdf` (two columns), `output/team_goal_picks.csv`, `output/team_goal_probabilities.csv`.

Run (the PDF needs reportlab: `pip install reportlab`):

```bash
python3 team_goal_picks.py          # writes CSVs and PDF
python3 team_goal_picks.py --no-pdf # CSVs only, no reportlab needed
```

Limits: the Poisson model underweights blow-outs and surprise scorers, so real hit rates on the
over side are likely below the stated probabilities. No team is near-certain to score 3+. The
requested date 17/10/2025 is in the past, so this covers 17/10/2026.

## Verified-only picks (clean sheet)

`verified_picks.py` rebuilds the sheet from `data/verified_picks_2026-10-17_18.json`,
which lists only the picks that passed these checks: fixture and kick-off confirmed,
team news checked in at least two sources, and the goal-model probability at or above
the threshold (over 2 at >=50%, below 3 at >=93%). The script refuses to build the
sheet if a pick is missing from the model data, mis-matched, or below threshold.

Outputs: `output/verified_goal_picks_2026-10-17.pdf` (2 pages, landscape A4, with the
exclusions and their reasons) and `output/verified_goal_picks.csv`.

Run: `/tmp/pdfenv/bin/python verified_picks.py` (needs reportlab; `--no-pdf` for CSV only).
Sports4Cast's own accuracy record could not be verified, so its numbers are one input, not proof.

## Independent real-event predictions (current sheet — supersedes the two above)

`independent_picks.py` uses **no** prediction, odds or xG figure from any prediction
site. Inputs (`data/independent_inputs_2026-10-17_18.json`) are real events only:
goals scored/conceded this season, each league's goals-per-match average, and team
news. Rumours are labelled UNVERIFIED and carry no adjustment unless a club confirms
them. The earlier `team_goal_picks` and `verified_picks` sheets used copied site
baselines and are **superseded — do not use them**.

Run: `/tmp/pdfenv/bin/python independent_picks.py` (reportlab needed for the PDF).
Outputs: `output/independent_goal_picks_2026-10-17.pdf`, `output/independent_goal_picks.csv`.
On real-event data alone, no team clears the 55% over-2 bar; 12 teams clear the 93% below-3 bar.

## Expanded 54-match set incl. lower leagues (17 Oct 2026) — CURRENT

`data/independent_inputs_expanded_2026-10-17_18.json` extends the independent
model to **54 matches / 108 teams**: the original 11 top-flight fixtures plus
EFL Championship (11), EFL League One (11), EFL League Two (12) and Serie B (9),
Sat 17 – Sun 18 Oct 2026. Team P/GF/GA come from the BBC Sport league tables
(EFL) and the Wikipedia Serie B table; league goals-per-match from the
Wikipedia season pages. For lower-league teams no club-confirmed news was
sourced, so `attack_adj = 1.00` — those picks rest on real scoring/conceding
records only, and the PDF says so on every row.

Run: `python independent_picks.py --input data/independent_inputs_expanded_2026-10-17_18.json --pdf independent_goal_picks_50plus_2026-10-17.pdf --csv independent_goal_picks_50plus.csv`

Result at the same strict bars (over >= 55%, below >= 93%): **1 over-2 pick**
(Stockport County, 79.5%) and **36 below-3 picks**; the PDF also lists all 54
matches evaluated so the full scope is visible. Still no prediction site's
picks, odds or xG anywhere.

## Japan added (17 Oct 2026) — CURRENT

`data/independent_inputs_54plus_japan_2026-10-17_18.json` adds the Japanese
leagues playing on Saturday 17 Oct 2026: **J1 (8 fixtures), J2 (9), J3 (6)** —
77 matches / 154 teams in total. Because of the time difference, those matches
had already kicked off (several had finished) before this run. To keep the
model honest, every Japanese team's record was restored to its **pre-match**
state by subtracting the 17 Oct result from the published table (BBC Sport J1
table; J.League official standings for J2/J3); today's scores are never used
as model inputs. League rates: J1 2.91, J2 2.60 (260/100), J3 2.89 (289/100).
No club-confirmed news adjustment is applied to the new Japanese teams (1.00).

Run: `python independent_picks.py --input data/independent_inputs_54plus_japan_2026-10-17_18.json --pdf independent_goal_picks_japan_2026-10-17.pdf --csv independent_goal_picks_japan.csv`

## Match-TOTAL reading (confirmed by user 17 Oct 2026) — CURRENT

The user confirmed the intended meaning is the **combined match total**:
OVER = both teams together score a total of 2 goals or more; BELOW = both teams
together score a total of 3 goals or below. This replaces the single-team
reading used in the earlier sheets (they remain in the repo for audit).

`match_total_picks.py` sums the two team xGs from the independent model
(77-match Japan-expanded input) and treats the match total as Poisson.
Bars: P(total >= 2) >= 85% and P(total <= 3) >= 85%. Result: **15 OVER picks
and 16 BELOW picks**; P(total >= 3) ("more than 2") is printed alongside.
Outputs: `output/match_total_goal_picks_2026-10-17.pdf`, `output/match_total_goal_picks.csv`.
Run: `python match_total_picks.py`
