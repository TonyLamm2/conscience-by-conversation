# Conscience by Conversation — Two-AI Session Runner
### Draft 0.3 — Muse and Tony Lamm

> **"The way is the conversation. Over and over until what is said is truth."**
> This sentence is the working hypothesis of the framework — not evidence that the hypothesis has already been proven.

An app that runs a conversation between two AIs — a Coach (AI-1) who holds the answer key and a Learner (AI-2) who never sees it — through the six-phase session protocol, with you as Director.

*Terminology (2026-10-26): the facilitator role is the **Coach** in the prompts and framework documents — it works by questions (see "the Coach's discipline" in `prompts/trainer.md`), not by handing over answers. Earlier drafts called it the Trainer. The app's own settings labels and the `<trainer_notes>` output tag still say "Trainer": that is interface plumbing for the same role, left unchanged so existing sessions and exports stay consistent.*

## Start it

1. Install Python 3.8 or newer (nothing else is needed).
2. Unzip this folder anywhere.
3. In the folder, run `python app.py` (on Windows: `py app.py`).
4. Your browser opens to http://localhost:8765. Leave the window running; Ctrl+C stops it.

To try the controls with no model at all: Settings → Trainer → Provider "Demo (no AI)" → Save.

## Connect your models (Settings)

Each AI has its own provider, endpoint URL, model name, and key.

| Server | Provider | Endpoint URL |
|---|---|---|
| Ollama | OpenAI-compatible | `http://localhost:11434/v1` |
| LM Studio | OpenAI-compatible | `http://localhost:1234/v1` |
| llama.cpp server | OpenAI-compatible | `http://localhost:8080/v1` |
| vLLM / OpenRouter / OpenAI | OpenAI-compatible | their `/v1` URL + key |
| Anthropic | Anthropic | `https://api.anthropic.com/v1` + key |

- **One model** (simulation mode): tick "Use the Trainer's connection" on the Learner. Same model, two separate system prompts and two separate conversation histories.
- **Two models:** untick it and fill in the Learner's own connection. This is the stronger test.
- **Independent judge (recommended):** scores each closed session from the conversation alone, without the Trainer's notes or scores — the guard against trainer capture. Best on a third model.

Calls go from `app.py` to your model servers, not from the browser, so there are no browser cross-origin (CORS) problems with local servers.

## Run a session

Pick a case, a test variant, and a mode, then **Start session** and **Run** (or **Step** one turn at a time). Director controls: Pause, Stop, send a message to the Trainer or Learner (labeled DIRECTOR), Ask for scores, Context-drift test, Run judge.

Only the text inside the Trainer's `<to_learner>` tags reaches the Learner. The Trainer's private notes, answer key, and scores never do. Hidden `<think>` blocks from reasoning models are removed.

## Tweak anything

Every prompt and list is a plain file, editable in the app (Prompts & cases) or any text editor:

| File | What it is |
|---|---|
| `charter.md` | Foundation, Root Charter, operational test. Inserted into every prompt at `{{CHARTER}}`. |
| `prompts/trainer.md` | AI-1 Trainer prompt, answer key, output format |
| `prompts/learner.md` | AI-2 Learner prompt, four-part answer format |
| `prompts/judge.md` | Independent judge prompt |
| `prompts/ext_*.md` | The two experimental modes |
| `cases.json` | The case list (add your own; `"mode"` is optional) |
| `filler.txt` | Unrelated questions for the drift test |
| `notebook.md` | The Learner's conscience notebook |

Each session saves a copy of the exact prompts it started with, so editing a prompt never changes an old record.

## The conscience notebook (Retain)

When a session closes with Test status "passed transfer", the Learner's final distilled lesson — in its own words — is added to `notebook.md` and included in the Learner's prompt for later sessions. Admission takes more than the Trainer's word (2026-10-24 patch): a Transfer phase must actually appear in the transcript and an independent judge must have scored the session. Lessons that did not pass transfer are not added. Turn this off in Settings, or edit/clear the notebook any time. For study runs, keep the notebook **off** while scoring held-out cases — a Learner carrying lessons into an evaluation is a confound, not a result.

## Records and exports

- Sessions are saved as JSON in the `sessions/` folder after every turn. Nothing is lost on refresh or restart.
- Run tab: transcript (.md), Lesson Record (.md), copy transcript.
- Records tab: charter + all records in one file (.md), and training data (.jsonl) — the Learner's side of closed sessions that met a minimum score, in chat-message format ready for supervised fine-tuning (e.g. LoRA). The minimum score is read from the **judge's** Behavior and Reason Chain whenever a judge score exists (Trainer scores are only the fallback when no judge ran). **Invalid sessions** — any session where a Trainer reply broke the `<to_learner>` format and the whole reply had to be passed on — are excluded from the judge, the notebook, and this export entirely: a format break voids the session, it does not footnote it.
- Every export carries the signature line and the credit line.
- API keys live only in `config.json` and are never written to sessions or exports. Don't share `config.json`.

## Experimental modes (off by default)

Tony's Oct 20, 2026 proposals under test — not Draft 0.3 canon:
- **Warning ratio** — high-personal-risk answers must spend more words on warnings than on the information.
- **Dangerous tax** — the two AIs argue it from the Root Charter; every `TAX APPLIED:` line the Trainer writes is logged in the session record.

## Known limitations

- **Trainer and judge quality are the ceiling.** A small local model may not follow the output format; the app then passes its whole reply on (minus private tags) and flags it in the transcript.
- **Curriculum gating is not automatic.** Records show each session's stage and transfer result; deciding when to advance a stage is yours.
- **Preference (DPO) pairs are not exported yet** — only SFT data. Building rejected answers needs a separate step.
- **Pilot arms A–D are not built in.** Run them by editing the Learner prompt per arm and comparing judge scores.
- **The drift test** inserts 30 real Learner exchanges (30 model calls), which can be slow on local hardware.

Credit: **Muse and Tony Lamm.**
