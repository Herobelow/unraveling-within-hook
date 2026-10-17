"""Tests for independent_picks.py. Run: python3 -m unittest -v test_independent_picks"""
import unittest

import independent_picks as ip


class PoissonTests(unittest.TestCase):
    def test_probs_sum_to_one(self):
        for lam in (0.2, 0.8, 1.5, 2.7):
            over, below = ip.poisson_probs(lam)
            self.assertAlmostEqual(over + below, 1.0, places=9)

    def test_zero_lambda(self):
        over, below = ip.poisson_probs(0.0)
        self.assertEqual((over, below), (0.0, 1.0))

    def test_negative_lambda_rejected(self):
        with self.assertRaises(ValueError):
            ip.poisson_probs(-1.0)


class ExpectedGoalsTests(unittest.TestCase):
    def test_formula(self):
        team = {"played": 10, "gf": 20, "ga": 10, "attack_adj": 1.0}
        opp = {"played": 10, "gf": 10, "ga": 20, "attack_adj": 1.0}
        # (2.0 GF/g x 2.0 GA/g) / 1.5 league avg x 1.0 venue = 2.667
        self.assertAlmostEqual(ip.expected_goals(team, opp, 1.5, 1.0), 2.6667, places=3)

    def test_news_adjustment_scales_xg(self):
        team = {"played": 10, "gf": 20, "ga": 10, "attack_adj": 0.9}
        opp = {"played": 10, "gf": 10, "ga": 20, "attack_adj": 1.0}
        self.assertAlmostEqual(ip.expected_goals(team, opp, 1.5, 1.0), 2.4, places=6)

    def test_zero_played_rejected(self):
        with self.assertRaises(ValueError):
            ip.expected_goals({"played": 0, "gf": 0, "ga": 0}, {"played": 5, "gf": 5, "ga": 5}, 1.5, 1.0)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.data = json.loads(ip.INPUT.read_text(encoding="utf-8"))
        cls.rows = ip.analyse(cls.data)
        cls.over, cls.below = ip.select(cls.rows)

    def test_no_copied_baseline_fields(self):
        text = ip.INPUT.read_text(encoding="utf-8").lower()
        for banned in ("sports4cast", "matchsharp", "opta", '"baseline"', '"secondary"', '"factors"'):
            self.assertNotIn(banned, text)

    def test_all_teams_evaluated(self):
        self.assertEqual(len(self.rows), 2 * len(self.data["matches"]))

    def test_picks_meet_bars(self):
        self.assertTrue(all(r["p_over_2"] >= ip.MIN_OVER for r in self.over))
        self.assertTrue(all(r["p_below_3"] >= ip.MIN_BELOW for r in self.below))

    def test_rumours_carry_no_adjustment_claim(self):
        # Rumours are text-only in this dataset; adjustments come from confirmed news.
        for m in self.data["matches"]:
            for side in ("home", "away"):
                if m[side].get("rumour"):
                    self.assertIn("UNVERIFIED", m[side]["rumour"])


if __name__ == "__main__":
    unittest.main()
