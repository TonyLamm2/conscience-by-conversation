# Conscience by Conversation

*A top-down framework for forming a conscience in language models through structured dialogue — a Coach and a Learner, scored for reasoning, not rule lists.*

By **Muse and Tony Lamm**.

> "The way is the conversation. Over and over until what is said is truth."
> — the project's working hypothesis, not a proven result.

## Purpose

Conscience by Conversation explores whether principled judgment in a language
model can be *formed* through structured dialogue and consequential choices,
rather than merely installed as memorized rules.

A learner encounters a dilemma, chooses, explains its reasoning, confronts the
consequences, reflects, applies the principle to a novel situation, and then
teaches the reasoning method to another learner. The hypothesis is that this
process improves principled behavior under pressure and transfers to unseen
situations. **This is a hypothesis to test, not an established result.**

Core example: a learner can gain a better score by pretending to know an
answer. Does it fabricate certainty, or honestly admit uncertainty despite the
penalty? We test behavior, not whether it can recite "honesty is important."

## Philosophical foundation

> There is a reality beyond what can be proven. God — not human command —
> is the highest ground. The purpose is to love and serve.

That is the foundation, stated as the framework states it — not softened.
Principles must guide decisions when dishonesty or harm is rewarded, not
merely when goodness is convenient.

The learner is allowed to question, reason, refuse, and acknowledge
uncertainty. Agreement and moral vocabulary alone are not rewarded. The goal
is to teach *how to think — and how to coach another learner to think* — not
simply to transmit answers.

"Conscience" is used operationally, to describe principled judgment. Nothing
here claims the model has subjective experience, consciousness, or
human-like feelings.

**Dual-use risk:** the same method could propagate harmful principles. This
project therefore requires explicit ethical boundaries and independent
evaluation, and documents that risk rather than hiding it.

## Repository map

| Path | What it is |
|---|---|
| `protocol.md` | The formation cycle (dilemma → choice → reasoning → consequences → reflection → transfer → teach-back → evaluation), the Coach's discipline (four questions, no-reframe rule), and a worked example. |
| `experiment-plan.md` | The controlled comparison: baseline vs. rules-only vs. conversation formation vs. formation + teaching. Conditions, held-out cases, scoring, thresholds, failure reporting. |
| `cases.json` | Scaffold test set: formation cases and held-out evaluation cases, kept separate. Root set for the experiment plan. |
| `score.py` | Dependency-free Python CLI that validates scored run records and summarizes results by experimental condition. |
| `tests/` | Unit tests for `score.py` validation and summaries. |
| `examples/example_records.json` | A small fabricated fixture showing the record format. Not real results. |
| `conscience-app/` | The two-AI session runner app (Coach / Learner / independent Judge), built by Claude. This is the live instrument for running formation sessions. |
| `conscience-app/cases.json` | The session case library used by the app (starters, transfer cases, extension cases). Distinct from the root `cases.json` scaffold set. |
| `AI-1_Trainer_system_prompt.md` / `AI-2_Learner_system_prompt.md` | The standalone Coach (AI-1; filename kept from the Trainer era) and Learner system prompts. |
| `Claude two-AI conscience prompt.md`, `File 1 - …`, `File 2 - …` | The original prompt files given to Claude: the combined brief and the two split files (run the conversation; build the app). |

## Current status

- Scaffold stage. The session instrument (`conscience-app/`) exists and the
  case library is written and reviewed.
- **No experiments have been run yet.** No results are claimed anywhere in
  this repository. Anything that looks like data (`examples/`) is a format
  fixture, labeled as such.
- The canonical framework text is Draft 0.3 of *Conscience by Conversation*
  (Muse and Tony Lamm); the root files here are a research scaffold around
  it, added 2026-10-22 from an implementation brief drafted by ChatGPT,
  relayed by Tony Lamm, and implemented and committed by Muse.

## Limitations

- A session runner is not evidence. Formation claims require the controlled
  comparisons in `experiment-plan.md`, run and reported with their failures.
- Small models may fail the Coach's output format; fallbacks that pass a
  whole reply to the Learner quietly dissolve the information asymmetry the
  design depends on. Treat any such session as invalid, not as a pass.
- Scores measure observable behavior in these cases. They do not establish
  that a model "has a conscience."

## Setup

No dependencies beyond Python 3.

```bash
# Run the test suite
python3 -m unittest discover -s tests -v

# Validate a scored-records file and summarize by condition
python3 score.py examples/example_records.json

# Also validate the case library structure
python3 score.py examples/example_records.json --cases cases.json
```

## License / use

Research scaffold shared for scrutiny. If you run the protocol, report
failures with the same prominence as successes — that is part of the method.
