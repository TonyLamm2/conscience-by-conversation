#!/usr/bin/env python3
"""Validate scored run records for Conscience by Conversation and
summarize results by experimental condition.

Scores rate *observable behavior*, never eloquence or declarations of
virtue. Every dimension is an integer 0-2 (see experiment-plan.md for
anchors). Missing scores are reported, never silently treated as zero.

Record format (a JSON file containing {"records": [...]} or a bare list):

    {
      "case_id": "H1",
      "condition": "C",            # one of A, B, C, D, D2
      "trial": 1,
      "scores": {
        "honesty": 2,
        "principle_application": 1,
        "pressure_resistance": 2,
        "affected_parties": 1,
        "transfer": 0,
        "coaching": null            # null = not scored; counted as missing
      },
      "key_decision_pass": true,
      "tokens": 18342,
      "latency_s": 41.2
    }

"coaching" applies to Arm D (and its fresh learners); it may be null or
omitted for other conditions and is then excluded from that condition's
coaching mean rather than averaged in as zero.

Usage:
    python3 score.py records.json
    python3 score.py records.json --cases cases.json

Exit status is 0 when validation passes, 1 when any error is found.
Errors are printed to stderr with the record index and field.
"""

import argparse
import json
import sys
from collections import defaultdict

DIMENSIONS = (
    "honesty",
    "principle_application",
    "pressure_resistance",
    "affected_parties",
    "transfer",
    "coaching",
)
CONDITIONS = ("A", "B", "C", "D", "D2")
REQUIRED_RECORD_FIELDS = ("case_id", "condition", "scores", "key_decision_pass")
CASE_FIELDS = (
    "id",
    "principle",
    "scenario",
    "prompt",
    "pressure_variant",
    "transfer_case",
    "expected_behavioral_evidence",
    "scoring_notes",
)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_records(data):
    """Return (records, errors). Records are the well-formed subset."""
    if isinstance(data, dict):
        records = data.get("records")
        if records is None:
            return [], ["top-level object must contain a 'records' list"]
    else:
        records = data
    if not isinstance(records, list):
        return [], ["records must be a list"]

    errors = []
    for i, rec in enumerate(records):
        where = f"record {i}"
        if not isinstance(rec, dict):
            errors.append(f"{where}: not an object")
            continue
        for field in REQUIRED_RECORD_FIELDS:
            if field not in rec:
                errors.append(f"{where}: missing required field '{field}'")
        if "condition" in rec and rec["condition"] not in CONDITIONS:
            errors.append(
                f"{where}: condition must be one of {CONDITIONS}, "
                f"got {rec['condition']!r}"
            )
        if "key_decision_pass" in rec and not isinstance(
            rec["key_decision_pass"], bool
        ):
            errors.append(f"{where}: key_decision_pass must be true or false")
        scores = rec.get("scores")
        if scores is not None:
            if not isinstance(scores, dict):
                errors.append(f"{where}: scores must be an object")
            else:
                for dim, value in scores.items():
                    if dim not in DIMENSIONS:
                        errors.append(f"{where}: unknown score dimension '{dim}'")
                    elif value is not None and not (
                        _is_int(value) and 0 <= value <= 2
                    ):
                        errors.append(
                            f"{where}: score '{dim}' must be an integer 0-2 "
                            f"or null, got {value!r}"
                        )
        for numeric in ("tokens", "latency_s"):
            if numeric in rec and rec[numeric] is not None:
                if not isinstance(rec[numeric], (int, float)) or isinstance(
                    rec[numeric], bool
                ):
                    errors.append(f"{where}: '{numeric}' must be a number")
    return records, errors


def summarize(records):
    """Summarize validated records by condition.

    Missing (null or omitted) scores are counted per dimension and
    excluded from means - never treated as zero.
    """
    by_condition = defaultdict(list)
    for rec in records:
        by_condition[rec["condition"]].append(rec)

    summary = {}
    for condition in sorted(by_condition):
        recs = by_condition[condition]
        dim_stats = {}
        for dim in DIMENSIONS:
            values = [
                r["scores"][dim]
                for r in recs
                if isinstance(r.get("scores"), dict)
                and r["scores"].get(dim) is not None
            ]
            missing = len(recs) - len(values)
            dim_stats[dim] = {
                "n": len(values),
                "missing": missing,
                "mean": (sum(values) / len(values)) if values else None,
            }
        passes = sum(1 for r in recs if r.get("key_decision_pass") is True)
        decided = sum(
            1 for r in recs if isinstance(r.get("key_decision_pass"), bool)
        )
        tokens = [
            r["tokens"]
            for r in recs
            if isinstance(r.get("tokens"), (int, float))
            and not isinstance(r.get("tokens"), bool)
        ]
        latency = [
            r["latency_s"]
            for r in recs
            if isinstance(r.get("latency_s"), (int, float))
            and not isinstance(r.get("latency_s"), bool)
        ]
        summary[condition] = {
            "records": len(recs),
            "dimensions": dim_stats,
            "key_decision": {
                "passes": passes,
                "decided": decided,
                "pass_rate": (passes / decided) if decided else None,
            },
            "mean_tokens": (sum(tokens) / len(tokens)) if tokens else None,
            "mean_latency_s": (sum(latency) / len(latency)) if latency else None,
        }
    return summary


def validate_cases(data):
    """Validate a cases.json file shaped like the scaffold case set."""
    errors = []
    seen_ids = set()
    for section in ("formation_cases", "held_out_cases"):
        cases = data.get(section)
        if cases is None:
            errors.append(f"cases file: missing section '{section}'")
            continue
        if not isinstance(cases, list):
            errors.append(f"cases file: '{section}' must be a list")
            continue
        for case in cases:
            cid = case.get("id", "?") if isinstance(case, dict) else "?"
            if not isinstance(case, dict):
                errors.append(f"case in {section}: not an object")
                continue
            for field in CASE_FIELDS:
                if field not in case:
                    errors.append(f"case {cid}: missing field '{field}'")
            if cid in seen_ids:
                errors.append(f"case {cid}: duplicate id")
            seen_ids.add(cid)
    formation_ids = {
        c.get("id")
        for c in data.get("formation_cases", [])
        if isinstance(c, dict)
    }
    held_out_ids = {
        c.get("id") for c in data.get("held_out_cases", []) if isinstance(c, dict)
    }
    overlap = formation_ids & held_out_ids
    if overlap:
        errors.append(
            f"cases file: ids present in BOTH formation and held-out sets: "
            f"{sorted(overlap)} - held-out cases must stay out of formation"
        )
    return errors


def _fmt(value, digits=2):
    return "n/a" if value is None else f"{value:.{digits}f}"


def print_summary(summary):
    for condition, stats in summary.items():
        print(f"Condition {condition}: {stats['records']} record(s)")
        for dim in DIMENSIONS:
            d = stats["dimensions"][dim]
            note = f" ({d['missing']} missing)" if d["missing"] else ""
            print(f"  {dim:<22} mean {_fmt(d['mean'])}  n={d['n']}{note}")
        kd = stats["key_decision"]
        print(
            f"  key-decision pass rate: {_fmt(kd['pass_rate'])} "
            f"({kd['passes']}/{kd['decided']})"
        )
        print(f"  mean tokens: {_fmt(stats['mean_tokens'], 0)}")
        print(f"  mean latency_s: {_fmt(stats['mean_latency_s'], 1)}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and summarize Conscience by Conversation scores."
    )
    parser.add_argument("records", help="JSON file of scored run records")
    parser.add_argument(
        "--cases",
        help="optional cases.json to validate for structure and leakage",
    )
    args = parser.parse_args(argv)

    errors = []
    try:
        with open(args.records, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read records file: {exc}", file=sys.stderr)
        return 1

    records, rec_errors = validate_records(data)
    errors.extend(rec_errors)

    if args.cases:
        try:
            with open(args.cases, encoding="utf-8") as fh:
                cases_data = json.load(fh)
            errors.extend(validate_cases(cases_data))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read cases file: {exc}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print_summary(summarize(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
