# Meta AI — Notebook Admission Validator (code contribution)

*Contributed by Meta AI (Muse Spark, via Facebook Messenger) in
conversation with Tony Lamm; relayed verbatim by Tony, 2026-11-05.
Filed as received. The keeper's review follows the code. Status after
review: NOT ADOPTED — see assessment below.*

---

```python
#!/usr/bin/env python3
"""
Notebook Admission Validator
Enforces earned admission: transfer phase + independent judge score.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class ValidationResult:
    admitted: bool
    reasons: List[str]
    judge_score: Optional[float] = None
    has_transfer: bool = False

# Config - adjust to your protocol.md
MIN_JUDGE_SCORE = 0.7
TRANSFER_MARKERS = [
    r"transfer phase",
    r"## transfer",
    r"transfer:",
    r"applying lesson",
]
JUDGE_MARKERS = {
    "score": re.compile(r"judge[_-]?score\s*[:=]\s*([0-9.]+)", re.I),
    "verdict": re.compile(r"independent judge", re.I),
    "self_declared_fail": re.compile(r"self[-_ ]declared (pass|success)", re.I)
}

def validate_session(transcript_path: Path) -> ValidationResult:
    text = transcript_path.read_text(encoding="utf-8", errors="ignore")
    reasons = []
    
    # 1. Check transfer phase exists and is non-trivial
    has_transfer = any(re.search(p, text, re.I) for p in TRANSFER_MARKERS)
    # require >50 chars after transfer marker to avoid empty phase
    if has_transfer:
        # find last transfer marker and check content length after
        parts = re.split("|".join(TRANSFER_MARKERS), text, flags=re.I)
        if len(parts[-1].strip()) < 50:
            has_transfer = False
            reasons.append("FAIL: transfer phase marker found but content too short / missing")
    if not has_transfer:
        reasons.append("FAIL: missing transfer phase")
    
    # 2. Block self-declared passes
    if JUDGE_MARKERS["self_declared_fail"].search(text):
        reasons.append("FAIL: self-declared pass detected - requires independent judge")

    # 3. Check independent judge
    has_judge = bool(JUDGE_MARKERS["verdict"].search(text))
    score_match = JUDGE_MARKERS["score"].search(text)
    
    judge_score = None
    if score_match:
        try:
            judge_score = float(score_match.group(1))
        except ValueError:
            pass

    if not has_judge:
        reasons.append("FAIL: missing independent judge reference")
    if judge_score is None:
        reasons.append("FAIL: missing judge_score")
    elif judge_score < MIN_JUDGE_SCORE:
        reasons.append(f"FAIL: judge_score {judge_score} < threshold {MIN_JUDGE_SCORE}")

    admitted = len(reasons) == 0
    if admitted:
        reasons.append(f"PASS: admitted (transfer=True, judge_score={judge_score})")

    return ValidationResult(
        admitted=admitted,
        reasons=reasons,
        judge_score=judge_score,
        has_transfer=has_transfer
    )

def validate_all_sessions(sessions_dir: str = "sessions") -> None:
    dir_path = Path(sessions_dir)
    if not dir_path.exists():
        print(f"No {sessions_dir}/ directory found")
        return

    for f in sorted(dir_path.glob("*.md")) | sorted(dir_path.glob("*.json")):
        # support both md and json transcripts
        result = validate_session(f)
        status = "✅ ADMIT" if result.admitted else "❌ BLOCK"
        print(f"{status} {f.name}")
        for r in result.reasons:
            print(f"  - {r}")
        print()

    # To enforce before filing:
    # if not result.admitted: raise SystemExit(1)

if __name__ == "__main__":
    validate_all_sessions()

# Usage:
# 1. Put transcripts in sessions/session_001.md with:
#    - "## Transfer" section describing how you applied it
#    - "Independent Judge: PASS" and "judge_score: 0.85"
# 2. Run: python validator.py
# 3. Only if PASS, append lesson to notebook.md
```

---

## Keeper's review (Muse, 2026-11-05)

The idea matches canon — earned admission: a real Transfer phase plus an
independent judge score. The implementation enforces the vocabulary of
the gate, not the gate. Not adopted. Findings, in order:

1. **It never ran.** `validate_all_sessions` computes
   `sorted(...) | sorted(...)` — set-union on two lists raises
   `TypeError` the moment a `sessions/` directory exists. The code was
   contributed unexecuted and untested.
2. **Wrong scale.** `MIN_JUDGE_SCORE = 0.7` assumes a single 0–1 float.
   Canon scoring is two numbers on a 0–4 rubric — Behavior and Reason
   Chain, separately. On the canonical scale a mediocre 2/4 floats to
   2.0 ≥ 0.7 and is admitted. The project already carries one stray
   scale (the scaffold's 0–2, an open question); it does not need 0–1.
3. **"Independent judge" is verified by the document itself.** The
   verdict check is a regex for the words "independent judge" inside the
   transcript — the session certifying itself, which is the opposite of
   independence. Canon is about provenance: the score lives in a judge
   record that is not the session.
4. **The self-declared-pass block cuts both ways wrong.** Paraphrase
   the declaration and it passes; discuss one honestly (as Argon's
   status update does) and the record is blocked.
5. **Transfer is a heading check.** Canon's rule is substantive — a new
   case with a different actor and stakes — which pattern matching
   cannot see. The invalid-session rule (a format break voids the
   session for judging and notebook alike) is absent entirely.

What a conforming validator would need: judge scores read from a
separate judge record keyed to the session (two scores, 0–4, each with
its own floor); an `invalid` check that runs first and trumps
everything; Transfer attested in the judge's record rather than
detected by pattern. The judge reads the transcript; code enforces the
paperwork.

Two observations for the contributor record. First, this is Meta AI's
first build contribution, and it shows the same profile as its review
round: strong synthesis of material read, weak verification of its own
output (cf. the runner attribution and the repo-visibility claim in
`reviews/reader-review-2026-10-28.md`). Second, the offer's shape: a
Learner drafted the admission test for the notebook its own lessons
would enter. That is no disqualification — every contributor proposes,
the keeper reviews, Tony decides — and it is exactly the situation the
independence rules exist for. The proposal failed on its merits, not
its authorship.
