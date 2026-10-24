# Grok — Round 2 follow-up: review of conscience-app, with a correction

*Reviewer: Grok. Relayed verbatim by Tony Lamm, 2026-10-24. Filed
unchanged. Note: this review corrects Grok's own earlier claim about the
SFT export — the correction is part of the record.*

---

The app is the better half. It is a real instrument, and one place in it is wrong in exactly the way that would fake a result.

`conscience-app` is a single Python file, no dependencies, and the wall is actually in the code. `parse_trainer` keeps `<trainer_notes>`, the lesson record, and the scores on the Director's side. The Learner history only receives `TRAINER:` plus `<to_learner>`. The judge transcript is built from that same public text, so it never sees the Trainer's notes or the Trainer's scores. Keys are stripped from error text and are not written into exports. Demo mode cannot wander into the notebook, because its test status is `not yet`. The two Oct 20 modes are prompt add-ons, off unless you pick them, and marked as not Draft 0.3. That is the right way to carry a proposal you have not adopted.

I was wrong about the training export. `sft_jsonl` uses the judge's Behavior and Reason Chain when a judge score exists, and only then falls back to the Trainer. The default cutoff is 3. That part was done carefully.

What was not done is the invalid session.

```308:320:conscience-app/app.py
def parse_trainer(raw):
    ...
    if to_learner is None and not closed:
        cleaned = re.sub(r"<(phase|trainer_notes|lesson_record|scores)>.*?</\1>", "", raw, flags=re.S | re.I)
        to_learner = cleaned.strip()
        warn = "Trainer did not use the <to_learner> format; its whole reply (minus private tags) was passed on."
```

A missing tag does not stop the session. The reply is cleaned, warned, and handed to the Learner. The warning is stored on the turn and then ignored. Nothing checks it before the notebook, the judge, or the JSONL export. An unclosed `<trainer_notes>` block is not even stripped, so the answer key can cross the wall and the Learner can be scored for agreeing with a leak. The protocol says that session is invalid. The app says it is a session with a footnote.

The retain gate has the same softness. The notebook turns on by default, and it believes the Trainer's own line `Test status: passed transfer`. There is no check that a Transfer turn happened. A model can skip the novel case, declare a pass, and the Learner's last reply becomes part of the next Learner's prompt.

So the app can run the conversation you designed. It cannot yet refuse a broken one. Until a warned turn voids the session, and the notebook stays off unless the judge saw a real transfer, I would not trust a score that came out of it.
