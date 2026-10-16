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
