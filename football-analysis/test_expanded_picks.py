"""Tests for the expanded 54-match independent set (incl. lower leagues)."""
import json
import unittest
from pathlib import Path

import independent_picks as ip

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "data" / "independent_inputs_expanded_2026-10-17_18.json").read_text(encoding="utf-8"))

BANNED_KEYS = {"odds", "sports4cast", "matchsharp", "opta", "baseline", "bookmaker"}


def flatten_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k.lower()
            yield from flatten_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from flatten_keys(v)


class ExpandedDataTests(unittest.TestCase):
    def test_at_least_50_matches(self):
        self.assertGreaterEqual(len(DATA["matches"]), 50)

    def test_lower_leagues_included(self):
        comps = {m["competition"] for m in DATA["matches"]}
        for league in ("EFL Championship", "EFL League One", "EFL League Two", "Serie B"):
            self.assertIn(league, comps)

    def test_no_copied_prediction_fields(self):
        self.assertTrue(BANNED_KEYS.isdisjoint(set(flatten_keys(DATA))))

    def test_every_team_has_real_record(self):
        for m in DATA["matches"]:
            for side in ("home", "away"):
                t = m[side]
                self.assertGreater(t["played"], 0, t)
                self.assertGreaterEqual(t["gf"], 0)
                self.assertGreaterEqual(t["ga"], 0)

    def test_lower_league_teams_unadjusted(self):
        # Expansion honesty rule: no sourced news => no silent adjustment.
        lower = {"EFL Championship", "EFL League One", "EFL League Two", "Serie B"}
        for m in DATA["matches"]:
            if m["competition"] in lower:
                for side in ("home", "away"):
                    self.assertEqual(m[side].get("attack_adj", 1.0), 1.0)


class ExpandedModelTests(unittest.TestCase):
    def test_picks_respect_confidence_bars(self):
        rows = ip.analyse(DATA)
        self.assertEqual(len(rows), 2 * len(DATA["matches"]))
        over, below = ip.select(rows)
        self.assertTrue(all(r["p_over_2"] >= ip.MIN_OVER for r in over))
        self.assertTrue(all(r["p_below_3"] >= ip.MIN_BELOW for r in below))
        # The bars must actually filter: far fewer picks than teams evaluated.
        self.assertLess(len(over) + len(below), len(rows) // 2)


if __name__ == "__main__":
    unittest.main()
