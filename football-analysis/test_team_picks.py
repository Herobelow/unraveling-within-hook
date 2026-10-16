"""Tests for team_goal_picks.py (logic only; PDF step not required). Run: python3 -m unittest -v test_team_picks"""
import unittest

import predict as p
import team_goal_picks as t


class TeamProbabilityTests(unittest.TestCase):
    def test_over_and_below_sum_to_one(self):
        for lam in (0.5, 1.2, 2.6, 3.3):
            over, below = t.team_goal_probs(lam)
            self.assertAlmostEqual(over + below, 1.0, places=9)

    def test_low_xg_team_is_mostly_below_three(self):
        over, below = t.team_goal_probs(0.7)
        self.assertGreater(below, 0.95)
        self.assertLess(over, 0.05)

    def test_over_probability_rises_with_xg(self):
        values = [t.team_goal_probs(lam)[0] for lam in (0.8, 1.6, 2.4, 3.2)]
        self.assertEqual(values, sorted(values))

    def test_matches_direct_poisson_formula(self):
        lam = 2.0
        expected_below = sum(p.poisson_pmf(lam)[:3])
        self.assertAlmostEqual(t.team_goal_probs(lam)[1], expected_below)


def _row(team, over, below):
    return {"team": team, "p_over_2": over, "p_below_3": below}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _row("A", 0.60, 0.40),
            _row("B", 0.49, 0.95),   # over just under the 0.50 bar -> excluded
            _row("C", 0.52, 0.97),
            _row("D", 0.10, 0.92),   # below 0.93 bar -> excluded from below side
            _row("E", 0.05, 0.99),
        ]

    def test_over_side_requires_threshold(self):
        over, _ = t.select_picks(self.rows, min_over=0.50, min_below=0.93, n_below=10, total=50)
        self.assertEqual([r["team"] for r in over], ["A", "C"])

    def test_below_side_requires_threshold_and_is_sorted(self):
        _, below = t.select_picks(self.rows, min_over=0.50, min_below=0.93, n_below=10, total=50)
        self.assertEqual([r["team"] for r in below], ["E", "C", "B"])

    def test_total_cap_respected(self):
        # Over side has 2 qualifying teams (A, C); with a cap of 3 and 2 requested
        # below picks, the over side is trimmed to leave room for them.
        over, below = t.select_picks(self.rows, min_over=0.50, min_below=0.93, n_below=2, total=3)
        self.assertEqual(len(over) + len(below), 3)
        self.assertEqual(len(over), 2)   # both qualifying over teams kept
        self.assertEqual(len(below), 1)  # only one slot left for below-3 picks

    def test_no_pick_below_thresholds(self):
        over, below = t.select_picks(self.rows, min_over=0.50, min_below=0.93, n_below=45, total=50)
        self.assertTrue(all(r["p_over_2"] >= 0.50 for r in over))
        self.assertTrue(all(r["p_below_3"] >= 0.93 for r in below))


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysed, _ = t.load_analysed()
        cls.rows = t.team_rows(cls.analysed)

    def test_every_match_gives_two_teams(self):
        self.assertEqual(len(self.rows), 2 * len(self.analysed))

    def test_probabilities_are_valid(self):
        for r in self.rows:
            self.assertTrue(0 <= r["p_over_2"] <= 1)
            self.assertTrue(0 <= r["p_below_3"] <= 1)
            self.assertAlmostEqual(r["p_over_2"] + r["p_below_3"], 1.0, places=9)

    def test_final_picks_meet_rules(self):
        over, below = t.select_picks(self.rows)
        self.assertLessEqual(len(over) + len(below), 50)
        self.assertTrue(all(r["p_over_2"] >= 0.50 for r in over))
        self.assertTrue(all(r["p_below_3"] >= 0.93 for r in below))


if __name__ == "__main__":
    unittest.main()
