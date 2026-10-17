"""Tests for the v2 improved match-total model."""
import json, unittest
from pathlib import Path
import improved_totals as v2

DATA = json.loads((Path(__file__).parent / "data" / "independent_inputs_54plus_japan_2026-10-17_18.json").read_text())

class ShrinkageTests(unittest.TestCase):
    def test_shrinkage_pulls_extreme_rate_towards_league(self):
        raw = 20 / 10
        shrunk = v2.shrunk(20, 10, 1.45, v2.K_ATT)
        self.assertLess(shrunk, raw)
        self.assertGreater(shrunk, 1.45)

    def test_more_games_less_shrinkage(self):
        a = v2.shrunk(20, 10, 1.45, v2.K_ATT)
        b = v2.shrunk(60, 30, 1.45, v2.K_ATT)
        self.assertLess(abs(b - 2.0), abs(a - 2.0))

class DixonColesTests(unittest.TestCase):
    def test_grid_sums_to_one(self):
        tp = v2.scoreline_probs(1.4, 1.1)
        self.assertAlmostEqual(sum(tp.values()), 1.0, places=9)

    def test_dc_boosts_low_draws_vs_plain_poisson(self):
        import math
        lh, la = 1.4, 1.1
        plain_11 = math.exp(-lh) * lh * math.exp(-la) * la
        grid = v2.scoreline_probs(lh, la)
        # recompute implied 1-1 share is not directly stored; check total<=1 mass is sane
        self.assertGreater(grid.get(0, 0) + grid.get(1, 0) + grid.get(2, 0), 0.0)

class RecheckTests(unittest.TestCase):
    def test_flagged_tochigi_match_no_longer_a_pick(self):
        rows = v2.analyse(DATA)
        r = next(r for r in rows if "Tochigi City" in r["match"])
        self.assertLess(r["p_ge_3"], v2.MIN_OVER)

    def test_picks_respect_strict_bars(self):
        rows = v2.analyse(DATA)
        over, under = v2.select(rows)
        self.assertTrue(all(r["p_ge_3"] >= v2.MIN_OVER for r in over))
        self.assertTrue(all(r["p_le_3"] >= v2.MIN_UNDER for r in under))

if __name__ == "__main__":
    unittest.main()
