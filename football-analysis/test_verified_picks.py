"""Tests for verified_picks.py. Run: python3 -m unittest -v test_verified_picks"""
import unittest

import team_goal_picks as tgp
import verified_picks as v


def _rows():
    return [
        {"match_id": "M1", "team": "Alpha", "match": "Alpha v Beta", "competition": "L",
         "window": "Sat", "xg": 3.29, "p_over_2": 0.64, "p_below_3": 0.36},
        {"match_id": "M2", "team": "Gamma", "match": "Delta v Gamma", "competition": "L",
         "window": "Sun", "xg": 0.67, "p_over_2": 0.03, "p_below_3": 0.97},
    ]


def _pick(match_id, team, side):
    return {"match_id": match_id, "team": team, "side": side, "kickoff_utc": "Sat 17 Oct 12:00",
            "news": "n", "sources": "s"}


class AttachTests(unittest.TestCase):
    def test_valid_picks_get_probabilities(self):
        verified = {"picks": [_pick("M1", "Alpha", "over2"), _pick("M2", "Gamma", "below3")]}
        out = v.attach_probabilities(verified, _rows())
        self.assertEqual(len(out), 2)
        self.assertAlmostEqual(out[0]["probability"], 0.64)
        self.assertAlmostEqual(out[1]["probability"], 0.97)

    def test_unknown_team_rejected(self):
        verified = {"picks": [_pick("M1", "Missing", "over2")]}
        with self.assertRaises(ValueError):
            v.attach_probabilities(verified, _rows())

    def test_wrong_side_of_fixture_rejected(self):
        verified = {"picks": [_pick("M2", "Alpha", "over2")]}
        with self.assertRaises(ValueError):
            v.attach_probabilities(verified, _rows())

    def test_below_threshold_rejected(self):
        verified = {"picks": [_pick("M2", "Gamma", "over2")]}
        with self.assertRaises(ValueError):
            v.attach_probabilities(verified, _rows())

    def test_duplicate_match_rejected(self):
        verified = {"picks": [_pick("M1", "Alpha", "over2"), _pick("M1", "Alpha", "over2")]}
        with self.assertRaises(ValueError):
            v.attach_probabilities(verified, _rows())

    def test_unknown_side_rejected(self):
        verified = {"picks": [_pick("M1", "Alpha", "exactly3")]}
        with self.assertRaises(ValueError):
            v.attach_probabilities(verified, _rows())


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verified = v.load_verified()
        analysed, _ = tgp.load_analysed()
        cls.picks = v.attach_probabilities(cls.verified, tgp.team_rows(analysed))

    def test_all_verified_picks_resolve(self):
        self.assertEqual(len(self.picks), len(self.verified["picks"]))

    def test_both_sides_present(self):
        sides = {p["side"] for p in self.picks}
        self.assertEqual(sides, {"over2", "below3"})

    def test_every_pick_has_news_and_sources(self):
        for p in self.picks:
            self.assertTrue(p["news"].strip())
            self.assertTrue(p["sources"].strip())

    def test_exclusion_reasons_given(self):
        for e in self.verified["excluded"]:
            self.assertTrue(e["reason"].strip())


if __name__ == "__main__":
    unittest.main()
