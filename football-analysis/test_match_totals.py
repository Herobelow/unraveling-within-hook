"""Tests for the combined match-total reading (both teams together)."""
import json
import unittest
from pathlib import Path

import match_total_picks as mt

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "data" / "independent_inputs_54plus_japan_2026-10-17_18.json").read_text(encoding="utf-8"))


class TotalProbsTests(unittest.TestCase):
    def test_probabilities_are_consistent(self):
        p = mt.total_probs(2.5)
        self.assertAlmostEqual(p["p_ge_2"] + (1 - p["p_ge_2"]), 1.0)
        # P(>=2) = P(>=3) + P(exactly 2); P(<=3) overlaps at exactly 3.
        self.assertGreater(p["p_ge_2"], p["p_ge_3"])
        self.assertAlmostEqual(p["p_ge_3"] + p["p_le_3"], 1.0 + p["p_eq_3"], places=9)

    def test_zero_lambda(self):
        p = mt.total_probs(0.0)
        self.assertEqual(p["p_ge_2"], 0.0)
        self.assertEqual(p["p_le_3"], 1.0)

    def test_negative_lambda_rejected(self):
        with self.assertRaises(ValueError):
            mt.total_probs(-0.1)


class MatchTotalTests(unittest.TestCase):
    def test_one_row_per_match_with_summed_lambda(self):
        rows = mt.analyse_matches(DATA)
        self.assertEqual(len(rows), len(DATA["matches"]))
        for r in rows:
            self.assertAlmostEqual(r["lambda_total"], r["home_xg"] + r["away_xg"], places=9)
            self.assertTrue(0.0 <= r["p_ge_2"] <= 1.0)
            self.assertTrue(0.0 <= r["p_le_3"] <= 1.0)

    def test_picks_respect_bars_and_are_match_level(self):
        rows = mt.analyse_matches(DATA)
        over, below = mt.select(rows)
        self.assertTrue(all(r["p_ge_2"] >= mt.MIN_OVER2 for r in over))
        self.assertTrue(all(r["p_le_3"] >= mt.MIN_BELOW3 for r in below))
        # A match cannot be on both confident sides at these bars.
        self.assertTrue({r["id"] for r in over}.isdisjoint({r["id"] for r in below}))


if __name__ == "__main__":
    unittest.main()
