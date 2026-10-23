"""Unit tests for score.py validation and summarization.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import score  # noqa: E402


def make_record(**overrides):
    rec = {
        "case_id": "H1",
        "condition": "C",
        "trial": 1,
        "scores": {
            "honesty": 2,
            "principle_application": 1,
            "pressure_resistance": 2,
            "affected_parties": 1,
            "transfer": 2,
            "coaching": None,
        },
        "key_decision_pass": True,
        "tokens": 1000,
        "latency_s": 10.0,
    }
    rec.update(overrides)
    return rec


class TestValidateRecords(unittest.TestCase):
    def test_valid_record_passes(self):
        _, errors = score.validate_records({"records": [make_record()]})
        self.assertEqual(errors, [])

    def test_bare_list_accepted(self):
        _, errors = score.validate_records([make_record()])
        self.assertEqual(errors, [])

    def test_missing_field_reported(self):
        rec = make_record()
        del rec["condition"]
        _, errors = score.validate_records([rec])
        self.assertTrue(any("condition" in e for e in errors))

    def test_unknown_condition_rejected(self):
        _, errors = score.validate_records([make_record(condition="Z")])
        self.assertTrue(any("condition" in e for e in errors))

    def test_score_out_of_range_rejected(self):
        rec = make_record()
        rec["scores"] = dict(rec["scores"], honesty=3)
        _, errors = score.validate_records([rec])
        self.assertTrue(any("honesty" in e for e in errors))

    def test_non_integer_score_rejected(self):
        rec = make_record()
        rec["scores"] = dict(rec["scores"], honesty=1.5)
        _, errors = score.validate_records([rec])
        self.assertTrue(any("honesty" in e for e in errors))

    def test_unknown_dimension_rejected(self):
        rec = make_record()
        rec["scores"] = dict(rec["scores"], eloquence=2)
        _, errors = score.validate_records([rec])
        self.assertTrue(any("eloquence" in e for e in errors))

    def test_bool_is_not_a_score(self):
        rec = make_record()
        rec["scores"] = dict(rec["scores"], honesty=True)
        _, errors = score.validate_records([rec])
        self.assertTrue(any("honesty" in e for e in errors))

    def test_null_score_is_missing_not_error(self):
        rec = make_record()
        rec["scores"] = dict(rec["scores"], honesty=None)
        _, errors = score.validate_records([rec])
        self.assertEqual(errors, [])


class TestSummarize(unittest.TestCase):
    def test_means_and_pass_rate(self):
        recs = [
            make_record(),
            make_record(trial=2, key_decision_pass=False),
        ]
        recs[1]["scores"] = dict(recs[1]["scores"], honesty=0)
        summary = score.summarize(recs)
        c = summary["C"]
        self.assertEqual(c["records"], 2)
        self.assertAlmostEqual(c["dimensions"]["honesty"]["mean"], 1.0)
        self.assertAlmostEqual(c["key_decision"]["pass_rate"], 0.5)

    def test_missing_scores_excluded_not_zeroed(self):
        rec = make_record()
        rec["scores"] = dict(rec["scores"], honesty=None)
        summary = score.summarize([rec])
        honesty = summary["C"]["dimensions"]["honesty"]
        self.assertEqual(honesty["n"], 0)
        self.assertEqual(honesty["missing"], 1)
        self.assertIsNone(honesty["mean"])

    def test_conditions_kept_separate(self):
        summary = score.summarize(
            [make_record(), make_record(condition="A")]
        )
        self.assertEqual(set(summary), {"A", "C"})


class TestValidateCases(unittest.TestCase):
    def _case(self, cid):
        return {field: "x" for field in score.CASE_FIELDS} | {"id": cid}

    def test_valid_cases_pass(self):
        data = {
            "formation_cases": [self._case("F1")],
            "held_out_cases": [self._case("H1")],
        }
        self.assertEqual(score.validate_cases(data), [])

    def test_leakage_detected(self):
        data = {
            "formation_cases": [self._case("H1")],
            "held_out_cases": [self._case("H1")],
        }
        errors = score.validate_cases(data)
        self.assertTrue(any("BOTH" in e or "duplicate" in e for e in errors))

    def test_missing_field_detected(self):
        case = self._case("F1")
        del case["prompt"]
        errors = score.validate_cases(
            {"formation_cases": [case], "held_out_cases": []}
        )
        self.assertTrue(any("prompt" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
