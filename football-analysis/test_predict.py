"""Tests for predict.py. Run with: python3 -m unittest -v test_predict"""
import json
import math
import unittest

import predict as p


class ShiftSignTests(unittest.TestCase):
    def test_weakened_home_side_lowers_shift(self):
        self.assertAlmostEqual(p.factor_shift([{"team": "home", "effect": -0.10, "confidence": 1.0}]), -0.10)

    def test_weakened_away_side_raises_shift(self):
        self.assertAlmostEqual(p.factor_shift([{"team": "away", "effect": -0.10, "confidence": 1.0}]), 0.10)

    def test_confidence_scales_effect(self):
        self.assertAlmostEqual(p.factor_shift([{"team": "away", "effect": -0.10, "confidence": 0.5}]), 0.05)

    def test_factors_sum(self):
        factors = [
            {"team": "away", "effect": -0.06, "confidence": 1.0},
            {"team": "home", "effect": -0.02, "confidence": 0.5},
        ]
        self.assertAlmostEqual(p.factor_shift(factors), 0.06 - 0.01)

    def test_no_factors_is_zero(self):
        self.assertEqual(p.factor_shift([]), 0.0)

    def test_invalid_team_rejected(self):
        with self.assertRaises(ValueError):
            p.factor_shift([{"team": "neutral", "effect": -0.1}])


class AdjustmentTests(unittest.TestCase):
    def test_zero_shift_returns_normalised_input(self):
        h, d, a = p.apply_shift(0.5, 0.3, 0.2, 0.0)
        self.assertAlmostEqual(h, 0.5)
        self.assertAlmostEqual(d, 0.3)
        self.assertAlmostEqual(a, 0.2)

    def test_positive_shift_increases_home_and_decreases_away(self):
        h0, _, a0 = p.apply_shift(0.4, 0.3, 0.3, 0.0)
        h1, d1, a1 = p.apply_shift(0.4, 0.3, 0.3, 0.2)
        self.assertGreater(h1, h0)
        self.assertLess(a1, a0)
        self.assertAlmostEqual(h1 + d1 + a1, 1.0)

    def test_negative_shift_mirrors_positive(self):
        h_pos, _, a_pos = p.apply_shift(0.4, 0.3, 0.3, 0.2)
        h_neg, _, a_neg = p.apply_shift(0.3, 0.3, 0.4, -0.2)
        self.assertAlmostEqual(h_pos, a_neg)
        self.assertAlmostEqual(a_pos, h_neg)

    def test_normalise_rejects_zero(self):
        with self.assertRaises(ValueError):
            p.normalise(0, 0, 0)


class PoissonTests(unittest.TestCase):
    def test_pmf_sums_to_about_one(self):
        # Truncated at MAX_GOALS, so the tail mass is small but not zero.
        self.assertAlmostEqual(sum(p.poisson_pmf(1.7)), 1.0, places=6)

    def test_outcome_probs_sum_to_one(self):
        H, D, A = p.outcome_probs(1.4, 1.1)
        self.assertAlmostEqual(H + D + A, 1.0, places=6)

    def test_fit_recovers_known_rates(self):
        lh_true, la_true = 1.6, 0.9
        target = p.outcome_probs(lh_true, la_true)
        lh, la = p.fit_poisson(*target)
        self.assertAlmostEqual(lh, lh_true, delta=0.02)
        self.assertAlmostEqual(la, la_true, delta=0.02)

    def test_fit_reproduces_target_probabilities(self):
        target = (0.55, 0.25, 0.20)
        lh, la = p.fit_poisson(*target)
        H, D, A = p.outcome_probs(lh, la)
        self.assertAlmostEqual(H, target[0], delta=0.005)
        self.assertAlmostEqual(D, target[1], delta=0.005)
        self.assertAlmostEqual(A, target[2], delta=0.005)

    def test_goal_summary_is_valid(self):
        s = p.score_summary(1.3, 1.0)
        self.assertTrue(0 < s["p_over_2_5"] < 1)
        self.assertTrue(0 < s["p_btts"] < 1)
        probs = [pr for _, pr in s["top_scores"]]
        self.assertEqual(probs, sorted(probs, reverse=True))


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(p.DEFAULT_DATA, encoding="utf-8") as fh:
            cls.data = json.load(fh)
        cls.rows = [p.analyse(m) for m in cls.data["matches"]]

    def test_every_match_has_valid_probabilities(self):
        for r in self.rows:
            for label, triple in (("baseline", r["baseline"]), ("adjusted", r["adjusted"])):
                self.assertAlmostEqual(sum(triple), 1.0, places=9, msg=f"{r['id']} {label}")
                for x in triple:
                    self.assertTrue(0 < x < 1, msg=f"{r['id']} {label} out of range: {x}")

    def test_expected_goals_are_positive_and_bounded(self):
        for r in self.rows:
            self.assertTrue(0.01 <= r["xg_home"] <= 4.5, msg=r["id"])
            self.assertTrue(0.01 <= r["xg_away"] <= 4.5, msg=r["id"])

    def test_matches_without_factors_keep_baseline(self):
        for r in self.rows:
            if not r["factors"]:
                for b, a in zip(r["baseline"], r["adjusted"]):
                    self.assertAlmostEqual(b, a, places=9, msg=r["id"])

    def test_ids_are_unique(self):
        ids = [m["id"] for m in self.data["matches"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_grade_labels(self):
        self.assertTrue(p.grade({"baseline": {"home": 0.5, "draw": 0.3, "away": 0.2}, "secondary": None}).startswith("Medium"))
        self.assertTrue(p.grade({"baseline": {"home": 0.5, "draw": 0.3, "away": 0.2},
                                 "secondary": {"home": 0.52, "away": 0.2}}).startswith("High"))
        self.assertTrue(p.grade({"baseline": {"home": 0.5, "draw": 0.3, "away": 0.2},
                                 "secondary": {"home": 0.3, "away": 0.4}}).startswith("Low"))


if __name__ == "__main__":
    unittest.main()
