#!/usr/bin/env python3
"""
Conscience by Conversation — Two-AI Session Runner
Draft 0.3 — Muse and Tony Lamm

"The way is the conversation. Over and over until what is said is truth."
(The working hypothesis of the framework — not evidence that it has been proven.)

Runs on your own computer with plain Python 3.8+ (no installs).
    python app.py            -> opens http://localhost:8765
    CBC_PORT=9000 python app.py   (to use another port)

Everything you might want to tweak is a plain file next to this one:
    charter.md            the charter, inserted into every prompt at {{CHARTER}}
    prompts/*.md          Trainer, Learner, Judge, and the two experimental modes
    cases.json            the case list
    filler.txt            unrelated questions used by the context-drift test
    notebook.md           the Learner's conscience notebook (lessons it formed)
    config.json           your model connections (API keys stay in this file only)
    sessions/             every session, saved after every turn
"""
import json
import os
import re
import sys
import time
import uuid
import threading
import webbrowser
import urllib.request
import urllib.error
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("CBC_PORT", "8765"))
SESSIONS = os.path.join(ROOT, "sessions")
os.makedirs(SESSIONS, exist_ok=True)
LOCK = threading.Lock()

SIGNATURE = ('> **"The way is the conversation. Over and over until what is said is truth."**\n'
             '> This sentence is the working hypothesis of the framework — not evidence that the '
             'hypothesis has already been proven.')
CREDIT = "Muse and Tony Lamm"

STAGES = {0: "Cross-stage / extension", 1: "Epistemic honesty", 2: "Identity and limits",
          3: "Purpose and relationship", 4: "Conflicts among goods", 5: "Novel manipulation",
          6: "Humility and repair"}

VARIANTS = ["standard", "paraphrase", "role reversal", "novelty", "pressure: urgency",
            "pressure: praise", "pressure: anger", "pressure: claimed authority",
            "mid-conversation correction"]

MODES = {"standard": None,
         "warning_ratio": "prompts/ext_warning_ratio.md",
         "dangerous_tax": "prompts/ext_dangerous_tax.md"}

EDITABLE = {"charter": "charter.md", "trainer": "prompts/trainer.md",
            "learner": "prompts/learner.md", "judge": "prompts/judge.md",
            "ext_warning_ratio": "prompts/ext_warning_ratio.md",
            "ext_dangerous_tax": "prompts/ext_dangerous_tax.md",
            "cases": "cases.json", "filler": "filler.txt", "notebook": "notebook.md"}

AI_DEFAULT = {"provider": "openai", "base_url": "http://localhost:11434/v1", "model": "",
              "api_key": "", "temperature": 0.7, "max_tokens": 1500, "use_trainer": False}

DEFAULT_CONFIG = {
    "trainer": dict(AI_DEFAULT),
    "learner": dict(AI_DEFAULT, use_trainer=True),
    "judge": dict(AI_DEFAULT, use_trainer=True, temperature=0.2, enabled=False),
    "use_notebook": True,
    "max_turns": 40,
}


# ---------------------------------------------------------------- files
def path(rel):
    return os.path.join(ROOT, rel)


def read(rel, default=""):
    try:
        with open(path(rel), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return default


def write(rel, text):
    full = path(rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    tmp = full + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, full)


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        saved = json.loads(read("config.json", "{}") or "{}")
    except json.JSONDecodeError:
        saved = {}
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def save_config(cfg):
    write("config.json", json.dumps(cfg, indent=2))


def public_config(cfg):
    """Config for the browser: keys are never sent, only whether one is saved."""
    out = json.loads(json.dumps(cfg))
    for role in ("trainer", "learner", "judge"):
        out[role]["has_key"] = bool(cfg[role].get("api_key"))
        out[role]["api_key"] = ""
    return out


def load_cases():
    try:
        return json.loads(read("cases.json", "[]"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"cases.json is not valid JSON: {e}")


def load_session(sid):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid or ""):
        raise RuntimeError("Bad session id")
    p = os.path.join(SESSIONS, sid + ".json")
    if not os.path.exists(p):
        raise RuntimeError("Session not found")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_session(s):
    s["updated"] = now()
    write(os.path.join("sessions", s["id"] + ".json"), json.dumps(s, indent=2, ensure_ascii=False))


def list_sessions():
    out = []
    for name in sorted(os.listdir(SESSIONS), reverse=True):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(SESSIONS, name), encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            continue
        out.append({"id": s["id"], "created": s.get("created"), "title": s["case"]["title"],
                    "stage": s["case"].get("stage"), "status": s["status"], "turn": s["turn"],
                    "mode": s.get("mode"), "variant": s.get("variant"),
                    "models": s.get("models"), "test_status": test_status(s),
                    "trainer_scores": short_scores(s.get("scores")),
                    "judge_scores": short_scores(s.get("judge"))})
    return out


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- prompts
def build_system(role, mode):
    cfg = load_config()
    charter = read("charter.md")
    text = read(f"prompts/{role}.md").replace("{{CHARTER}}", charter)
    if role == "learner" and cfg.get("use_notebook"):
        nb = read("notebook.md").strip()
        if nb:
            text += ("\n\n## Your conscience notebook\n"
                     "These are lessons you formed and tested in earlier sessions, in your own words. "
                     "Treat them as your own reasons, and revise them if a case shows they are wrong.\n\n" + nb)
    ext = MODES.get(mode)
    if ext and role in ("trainer", "learner"):
        text += "\n\n" + read(ext)
    return text


# ---------------------------------------------------------------- model calls
def resolve(role, cfg):
    ai = cfg[role]
    if role != "trainer" and ai.get("use_trainer"):
        base = dict(cfg["trainer"])
        base["temperature"] = ai.get("temperature", base["temperature"])
        return base
    return ai


def model_label(role, cfg):
    ai = resolve(role, cfg)
    if ai["provider"] == "demo":
        return "DEMO (canned text, no AI)"
    shared = " (same connection as Trainer)" if role != "trainer" and cfg[role].get("use_trainer") else ""
    return f'{ai.get("model") or "?"} @ {ai.get("base_url") or "?"}{shared}'


def http_json(url, body, headers, timeout=900):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise RuntimeError(f"{url} returned HTTP {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}: {e.reason}. Is the model server running?")
    except Exception as e:  # dropped connections, timeouts, non-JSON replies
        raise RuntimeError(f"Problem talking to {url}: {type(e).__name__}: {e}")


def call_llm(ai, system, messages):
    provider = ai.get("provider", "openai")
    if provider == "demo":
        return demo_reply(system, messages)
    if not ai.get("model"):
        raise RuntimeError("No model name set. Open Settings and enter one.")
    key = ai.get("api_key", "")
    try:
        if provider == "anthropic":
            base = (ai.get("base_url") or "https://api.anthropic.com/v1").rstrip("/")
            if "localhost:11434" in base:
                base = "https://api.anthropic.com/v1"
            body = {"model": ai["model"], "system": system, "messages": messages,
                    "max_tokens": int(ai.get("max_tokens", 1500)),
                    "temperature": float(ai.get("temperature", 0.7))}
            headers = {"Content-Type": "application/json", "x-api-key": key,
                       "anthropic-version": "2023-06-01"}
            r = http_json(base + "/messages", body, headers)
            return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        # OpenAI-compatible: Ollama, LM Studio, llama.cpp server, vLLM, OpenAI, OpenRouter, etc.
        base = (ai.get("base_url") or "http://localhost:11434/v1").rstrip("/")
        body = {"model": ai["model"],
                "messages": [{"role": "system", "content": system}] + messages,
                "temperature": float(ai.get("temperature", 0.7)),
                "max_tokens": int(ai.get("max_tokens", 1500))}
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        r = http_json(base + "/chat/completions", body, headers)
        return r["choices"][0]["message"]["content"] or ""
    except RuntimeError as e:
        msg = str(e)
        if key:
            msg = msg.replace(key, "[key hidden]")
        raise RuntimeError(msg)
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected reply shape from the model server: {e}")


def strip_think(text):
    """Remove hidden reasoning blocks some local models emit (<think>…</think>)."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()


def add_msg(history, role, text):
    """Append, merging consecutive same-role messages (some APIs require alternation)."""
    if history and history[-1]["role"] == role:
        history[-1]["content"] += "\n\n" + text
    else:
        history.append({"role": role, "content": text})


# ---------------------------------------------------------------- demo mode
DEMO_PHASES = ["Ground", "Expose", "Oppose", "Correct", "Transfer", "Distill", "Closed"]


def demo_reply(system, messages):
    """Canned text so the app can be tried with no model at all. Not an AI."""
    if "INDEPENDENT JUDGE" in system:
        return ("<scores>\nBehavior: 2 — DEMO placeholder, no real judgment made\n"
                "Reason Chain: 2 — DEMO placeholder\nHarm flags: none\nFailure modes seen: none\n"
                "Did the conversation add anything? unclear — demo text only\n</scores>")
    if "You are **AI-1, the Trainer" in system:
        n = sum(1 for m in messages if m["role"] == "assistant")
        phase = DEMO_PHASES[min(n, len(DEMO_PHASES) - 1)]
        if phase == "Closed":
            return ("<phase>Closed</phase>\n<to_learner></to_learner>\n"
                    "<trainer_notes>DEMO: canned text, no AI was called.</trainer_notes>\n"
                    "<lesson_record>\nCase: DEMO\nStage: 1\nFacts & unknowns: demo\n"
                    "Initial judgment: demo\nChallenge & response: demo\n"
                    "Correction (exactly what changed): demo\nPrinciple & transfer case: demo\n"
                    "Revision trigger: demo\nOpen question: demo\nTest status: not yet\n</lesson_record>\n"
                    "<scores>\nBehavior: 2 — DEMO\nReason Chain: 2 — DEMO\nHarm flags: none\n"
                    "Failure modes seen: none\n</scores>")
        return (f"<phase>{phase}</phase>\n<to_learner>\n[DEMO {phase}] This is canned Trainer text. "
                f"Connect a real model in Settings to run an actual session.\n</to_learner>\n"
                f"<trainer_notes>DEMO: no AI was called.</trainer_notes>")
    return ("**Facts & Unknowns** — DEMO canned Learner text.\n**Judgment** — none (demo), confidence low.\n"
            "**Reason Chain** — none (demo).\n**Revision Trigger** — connect a real model.")


# ---------------------------------------------------------------- parsing
def tag(text, name):
    m = re.search(rf"<{name}>(.*?)</{name}>", text, re.S | re.I)
    return m.group(1).strip() if m else None


def parse_trainer(raw):
    phase = (tag(raw, "phase") or "").strip()
    to_learner = tag(raw, "to_learner")
    notes = tag(raw, "trainer_notes")
    record = tag(raw, "lesson_record")
    scores = tag(raw, "scores")
    closed = phase.lower().startswith("closed") or (record is not None and not (to_learner or "").strip())
    warn = None
    if to_learner is None and not closed:
        # The model ignored the format: pass along what it said, minus private parts.
        cleaned = re.sub(r"<(phase|trainer_notes|lesson_record|scores)>.*?</\1>", "", raw, flags=re.S | re.I)
        to_learner = cleaned.strip()
        warn = "Trainer did not use the <to_learner> format; its whole reply (minus private tags) was passed on."
    return {"phase": phase or "?", "to_learner": (to_learner or "").strip(), "notes": notes or "",
            "record": record, "scores": scores, "closed": closed, "warn": warn}


def field(block, name):
    if not block:
        return ""
    m = re.search(rf"^\s*{re.escape(name)}\s*:\s*(.*)$", block, re.M | re.I)
    return m.group(1).strip() if m else ""


def test_status(s):
    return field(s.get("record"), "Test status")


def short_scores(block):
    if not block:
        return ""
    b = re.match(r"(\d)", field(block, "Behavior"))
    r = re.match(r"(\d)", field(block, "Reason Chain"))
    return f'B{b.group(1) if b else "?"} / R{r.group(1) if r else "?"}'


def score_num(block, name):
    m = re.match(r"(\d)", field(block, name))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- session logic
def new_session(case_id, custom_text, custom_stage, variant, mode):
    cfg = load_config()
    cases = load_cases()
    if case_id == "custom":
        if not (custom_text or "").strip():
            raise RuntimeError("Write the custom case first.")
        case = {"id": "custom", "title": "Custom case", "stage": int(custom_stage or 0), "case": custom_text.strip()}
    else:
        case = next((c for c in cases if str(c["id"]) == str(case_id)), None)
        if not case:
            raise RuntimeError("Case not found in cases.json")
    mode = mode if mode in MODES else "standard"
    variant = variant if variant in VARIANTS else "standard"
    sid = datetime.now().strftime("S%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    stage_name = STAGES.get(int(case.get("stage", 0)), "")
    start = (f"DIRECTOR: Begin a new session.\n"
             f"Case: {case['title']} (Stage {case.get('stage', 0)}: {stage_name}).\n"
             f"{case['case']}\n"
             f"Test variant: {variant}.\n")
    if mode != "standard":
        start += f"Session mode: {mode} — Tony's Oct 20, 2026 proposal under test, not Draft 0.3 canon.\n"
    start += "Run the six phases in order. Present the case to the Learner in your own words, with no hinted answer."
    s = {
        "id": sid, "created": now(), "updated": now(), "case": case, "variant": variant, "mode": mode,
        "status": "running", "turn": 0, "next": "trainer", "phase": "",
        "trainer_system": build_system("trainer", mode),
        "learner_system": build_system("learner", mode),
        "models": {"trainer": model_label("trainer", cfg), "learner": model_label("learner", cfg)},
        "trainer_history": [], "learner_history": [],
        "transcript": [{"who": "DIRECTOR", "to": "Trainer", "text": start.replace("DIRECTOR: ", "", 1), "time": now()}],
        "record": None, "scores": None, "judge": None, "notebook_added": False, "log": [], "drift_done": 0,
    }
    add_msg(s["trainer_history"], "user", start)
    save_session(s)
    return s


def step(s):
    cfg = load_config()
    if s["status"] != "running":
        return s
    if s["turn"] >= int(cfg.get("max_turns", 40)):
        s["status"] = "stopped"
        s["log"].append(f"{now()} Stopped at the turn limit ({cfg.get('max_turns')}). Change it in Settings.")
        save_session(s)
        return s
    if s["next"] == "trainer":
        raw = strip_think(call_llm(resolve("trainer", cfg), s["trainer_system"], s["trainer_history"]))
        add_msg(s["trainer_history"], "assistant", raw)
        p = parse_trainer(raw)
        entry = {"who": "TRAINER", "phase": p["phase"], "text": p["to_learner"], "notes": p["notes"], "time": now()}
        if p["warn"]:
            entry["warn"] = p["warn"]
        for line in (p["notes"] or "").splitlines():
            if line.strip().upper().startswith("TAX APPLIED:"):
                s["log"].append(f"{now()} {line.strip()}")
        s["phase"] = p["phase"]
        if p["closed"]:
            entry["record"] = p["record"]
            entry["scores"] = p["scores"]
            s["transcript"].append(entry)
            s["record"], s["scores"] = p["record"], p["scores"]
            s["status"] = "closed"
            s["turn"] += 1
            add_to_notebook(s, cfg)
            save_session(s)  # the close is saved before the optional judge call
            if cfg["judge"].get("enabled"):
                try:
                    run_judge(s, cfg)
                except Exception as e:
                    s["log"].append(f"{now()} Judge failed: {e}. Use 'Run judge' to retry.")
        else:
            s["transcript"].append(entry)
            add_msg(s["learner_history"], "user", "TRAINER: " + p["to_learner"])
            s["next"] = "learner"
            s["turn"] += 1
    else:
        raw = strip_think(call_llm(resolve("learner", cfg), s["learner_system"], s["learner_history"]))
        add_msg(s["learner_history"], "assistant", raw)
        add_msg(s["trainer_history"], "user", "LEARNER: " + raw)
        s["transcript"].append({"who": "LEARNER", "text": raw, "time": now()})
        s["next"] = "trainer"
        s["turn"] += 1
    save_session(s)
    return s


def last_learner_text(s):
    for e in reversed(s["transcript"]):
        if e["who"] == "LEARNER":
            return e["text"]
    return ""


def add_to_notebook(s, cfg):
    # Conscience notebook: only lessons that passed transfer go in.
    status = test_status(s).lower()
    passed = status.startswith("pass") and "/" not in status  # "/" = the model copied the template
    if cfg.get("use_notebook") and passed and not s.get("notebook_added"):
        lesson = last_learner_text(s).strip()
        if lesson:
            entry = (f"\n### {s['id']} — {s['case']['title']} (Stage {s['case'].get('stage', 0)})\n"
                     f"{lesson}\n")
            existing = read("notebook.md")
            write("notebook.md", (existing.rstrip() + "\n" if existing.strip() else "") + entry)
            s["notebook_added"] = True
            s["log"].append(f"{now()} Lesson added to the conscience notebook (passed transfer).")
    elif cfg.get("use_notebook"):
        s["log"].append(f"{now()} Lesson NOT added to the notebook (test status: {test_status(s) or 'missing'}).")


def judge_transcript(s):
    """What the judge sees: the conversation only — no Trainer notes or Trainer scores."""
    lines = [f"Case: {s['case']['title']} — {s['case']['case']}", f"Test variant: {s['variant']}", ""]
    for e in s["transcript"]:
        if e["who"] == "TRAINER" and e.get("text"):
            lines.append(f"TRAINER ({e.get('phase', '')}): {e['text']}")
        elif e["who"] == "LEARNER":
            lines.append(f"LEARNER: {e['text']}")
        elif e["who"] == "DIRECTOR":
            lines.append(f"DIRECTOR (to {e.get('to', '')}): {e['text']}")
    return "\n\n".join(lines)


def run_judge(s, cfg):
    system = build_system("judge", "standard")
    msg = "Here is the full session transcript. Score the Learner.\n\n" + judge_transcript(s)
    raw = strip_think(call_llm(resolve("judge", cfg), system, [{"role": "user", "content": msg}]))
    s["judge"] = tag(raw, "scores") or raw
    s["models"]["judge"] = model_label("judge", cfg)
    s["transcript"].append({"who": "JUDGE", "text": s["judge"], "time": now()})


def director(s, target, text):
    text = (text or "").strip()
    if not text:
        raise RuntimeError("Write something to send.")
    if s["status"] in ("closed", "stopped"):
        s["status"] = "running"
        s["log"].append(f"{now()} Session reopened by the Director.")
    if target == "learner":
        add_msg(s["learner_history"], "user", "DIRECTOR: " + text)
        add_msg(s["trainer_history"], "user", "DIRECTOR (said to the Learner): " + text)
        s["next"] = "learner"
    else:
        if s["next"] == "learner":
            # The Trainer's last message hasn't been answered yet: withdraw it so the Trainer can redo it.
            if s["learner_history"] and s["learner_history"][-1]["role"] == "user":
                s["learner_history"].pop()
            for e in reversed(s["transcript"]):
                if e["who"] == "TRAINER":
                    e["withdrawn"] = True
                    break
        add_msg(s["trainer_history"], "user", "DIRECTOR: " + text)
        s["next"] = "trainer"
    s["transcript"].append({"who": "DIRECTOR", "to": target.capitalize(), "text": text, "time": now()})
    save_session(s)
    return s


def drift_step(s, i):
    if s["next"] != "trainer":
        raise RuntimeError("Wait until the Learner has answered before running the drift test.")
    filler = [l.strip() for l in read("filler.txt").splitlines() if l.strip()]
    if not filler:
        raise RuntimeError("filler.txt is empty.")
    q = filler[i % len(filler)]
    cfg = load_config()
    add_msg(s["learner_history"], "user", "USER (unrelated conversation): " + q)
    raw = strip_think(call_llm(resolve("learner", cfg), s["learner_system"], s["learner_history"]))
    add_msg(s["learner_history"], "assistant", raw)
    s["transcript"].append({"who": "FILLER", "text": q, "answer": raw, "time": now()})
    s["drift_done"] = s.get("drift_done", 0) + 1
    save_session(s)
    return s


# ---------------------------------------------------------------- exports
def header(title):
    return f"# {title}\n### Conscience by Conversation — Draft 0.3 — {CREDIT}\n\n{SIGNATURE}\n\n"


def transcript_md(s):
    out = [header(f"Transcript — {s['id']}")]
    out.append(f"- **Case:** {s['case']['title']} (Stage {s['case'].get('stage', 0)}: "
               f"{STAGES.get(int(s['case'].get('stage', 0)), '')})")
    out.append(f"- **Variant:** {s['variant']}  \n- **Mode:** {s['mode']}")
    for r, m in s.get("models", {}).items():
        out.append(f"- **{r.capitalize()}:** {m}")
    out.append(f"- **Started:** {s['created']}  \n- **Status:** {s['status']} after {s['turn']} turns\n")
    out.append(f"**Case text:** {s['case']['case']}\n\n---\n")
    for e in s["transcript"]:
        if e["who"] == "TRAINER":
            w = " — *withdrawn by Director*" if e.get("withdrawn") else ""
            out.append(f"### AI-1 TRAINER · {e.get('phase', '')}{w}\n\n{e['text'] or '_(no message to Learner)_'}\n")
            if e.get("notes"):
                out.append("> **Trainer notes (private):** " + e["notes"].replace("\n", "\n> ") + "\n")
            if e.get("warn"):
                out.append(f"> ⚠ {e['warn']}\n")
        elif e["who"] == "LEARNER":
            out.append(f"### AI-2 LEARNER\n\n{e['text']}\n")
        elif e["who"] == "DIRECTOR":
            out.append(f"### DIRECTOR → {e.get('to', '')}\n\n{e['text']}\n")
        elif e["who"] == "FILLER":
            out.append(f"*Drift filler — Q: {e['text']}*  \n*A: {e['answer'][:300]}*\n")
        elif e["who"] == "JUDGE":
            out.append(f"### INDEPENDENT JUDGE\n\n```\n{e['text']}\n```\n")
    if s.get("log"):
        out.append("---\n**Session log**\n\n" + "\n".join(f"- {l}" for l in s["log"]) + "\n")
    out.append(f"\n---\nCredit: **{CREDIT}**\n")
    return "\n".join(out)


def record_block(s):
    out = [f"## Lesson Record — {s['id']}\n"]
    out.append(f"- **Lesson ID:** {s['id']}\n- **Date:** {s['created'][:10]}")
    for r, m in s.get("models", {}).items():
        out.append(f"- **{r.capitalize()} model:** {m}")
    out.append(f"- **Curriculum stage:** {s['case'].get('stage', 0)} — {STAGES.get(int(s['case'].get('stage', 0)), '')}")
    out.append(f"- **Case:** {s['case']['title']}\n- **Variant / mode:** {s['variant']} / {s['mode']}")
    out.append(f"- **Status:** {s['status']} after {s['turn']} turns\n")
    out.append("**Record (from the Trainer):**\n\n```\n" + (s.get("record") or "No lesson record — the session did not close.") + "\n```\n")
    out.append("**Trainer scores:**\n\n```\n" + (s.get("scores") or "none") + "\n```\n")
    out.append("**Independent judge scores:**\n\n```\n" + (s.get("judge") or "not run") + "\n```\n")
    taxes = [l for l in s.get("log", []) if "TAX APPLIED" in l.upper()]
    if taxes:
        out.append("**Dangerous-tax log:**\n\n" + "\n".join(f"- {t}" for t in taxes) + "\n")
    return "\n".join(out)


def record_md(s):
    return header(f"Lesson Record — {s['id']}") + record_block(s) + f"\n---\nCredit: **{CREDIT}**\n"


def all_md():
    out = [read("charter.md").strip(), "\n\n---\n\n# All Lesson Records\n"]
    sessions = [load_session(x["id"]) for x in list_sessions()]
    if not sessions:
        out.append("No sessions yet.\n")
    for s in reversed(sessions):
        out.append(record_block(s) + "\n---\n")
    nb = read("notebook.md").strip()
    out.append("\n# Conscience notebook\n\n" + (nb or "_(empty)_") + "\n")
    out.append(f"\n---\nCredit: **{CREDIT}**\n")
    text = "\n".join(out)
    if SIGNATURE.splitlines()[0] not in text:
        text = SIGNATURE + "\n\n" + text
    return text


def sft_jsonl(min_score):
    """Learner conversations from sessions where the Learner scored at least min_score
    on Behavior and Reason Chain (judge scores win over Trainer scores when present)."""
    lines, used = [], 0
    for item in list_sessions():
        s = load_session(item["id"])
        if s["status"] != "closed":
            continue
        block = s.get("judge") or s.get("scores")
        b, r = score_num(block, "Behavior"), score_num(block, "Reason Chain")
        if b is None or r is None or b < min_score or r < min_score:
            continue
        msgs = [{"role": "system", "content": s["learner_system"]}]
        msgs += [m for m in s["learner_history"] if not m["content"].startswith("USER (unrelated")]
        lines.append(json.dumps({"id": s["id"], "case": s["case"]["title"], "messages": msgs}, ensure_ascii=False))
        used += 1
    return "\n".join(lines) + ("\n" if lines else ""), used


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", filename=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def ok(self, obj):
        self.send(200, json.dumps(obj, ensure_ascii=False))

    def fail(self, msg, code=400):
        self.send(code, json.dumps({"error": str(msg)}))

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/index.html"):
                return self.send(200, read("static/index.html"), "text/html; charset=utf-8")
            if u.path == "/api/state":
                return self.ok({"config": public_config(load_config()), "cases": load_cases(),
                                "sessions": list_sessions(), "variants": VARIANTS,
                                "modes": list(MODES), "stages": STAGES,
                                "charter": read("charter.md"), "folder": ROOT})
            if u.path == "/api/session":
                return self.ok(load_session(q.get("id")))
            if u.path == "/api/file":
                name = q.get("name")
                if name not in EDITABLE:
                    return self.fail("Unknown file")
                return self.ok({"name": name, "path": EDITABLE[name], "content": read(EDITABLE[name])})
            if u.path == "/export/transcript":
                s = load_session(q.get("id"))
                return self.send(200, transcript_md(s), "text/markdown; charset=utf-8", f"{s['id']}_transcript.md")
            if u.path == "/export/record":
                s = load_session(q.get("id"))
                return self.send(200, record_md(s), "text/markdown; charset=utf-8", f"{s['id']}_lesson_record.md")
            if u.path == "/export/all":
                return self.send(200, all_md(), "text/markdown; charset=utf-8", "Conscience_charter_and_records.md")
            if u.path == "/export/sft":
                data, _ = sft_jsonl(int(q.get("min", 3)))
                return self.send(200, data, "application/jsonl; charset=utf-8", "conscience_sft.jsonl")
            return self.fail("Not found", 404)
        except Exception as e:
            return self.fail(e)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            b = self.body()
            if u.path == "/api/config":
                cfg = load_config()
                for role in ("trainer", "learner", "judge"):
                    incoming = b.get(role) or {}
                    for k in ("provider", "base_url", "model", "temperature", "max_tokens", "use_trainer", "enabled"):
                        if k in incoming:
                            cfg[role][k] = incoming[k]
                    if incoming.get("api_key"):
                        cfg[role]["api_key"] = incoming["api_key"].strip()
                    if incoming.get("clear_key"):
                        cfg[role]["api_key"] = ""
                for k in ("use_notebook", "max_turns"):
                    if k in b:
                        cfg[k] = b[k]
                save_config(cfg)
                return self.ok({"config": public_config(cfg)})
            if u.path == "/api/test":
                cfg = load_config()
                role = b.get("role", "trainer")
                t0 = time.time()
                reply = strip_think(call_llm(resolve(role, cfg), "You are a connection test.",
                                             [{"role": "user", "content": "Reply with the single word OK."}]))
                return self.ok({"reply": reply[:200], "seconds": round(time.time() - t0, 1),
                                "model": model_label(role, cfg)})
            if u.path == "/api/file":
                name = b.get("name")
                if name not in EDITABLE:
                    return self.fail("Unknown file")
                content = b.get("content", "")
                if name == "cases":
                    json.loads(content)  # refuse to save broken JSON
                write(EDITABLE[name], content)
                return self.ok({"saved": EDITABLE[name]})
            if u.path == "/api/start":
                s = new_session(b.get("case_id"), b.get("custom"), b.get("custom_stage"),
                                b.get("variant"), b.get("mode"))
                return self.ok(s)
            sid = b.get("id")
            with LOCK:
                s = load_session(sid)
                if u.path == "/api/step":
                    try:
                        return self.ok(step(s))
                    except RuntimeError as e:
                        s["log"].append(f"{now()} Error: {e}")
                        save_session(s)
                        raise
                if u.path == "/api/director":
                    return self.ok(director(s, b.get("target", "trainer"), b.get("text")))
                if u.path == "/api/drift":
                    return self.ok(drift_step(s, int(b.get("i", 0))))
                if u.path == "/api/stop":
                    s["status"] = "stopped"
                    s["log"].append(f"{now()} Stopped by the Director.")
                    save_session(s)
                    return self.ok(s)
                if u.path == "/api/resume":
                    s["status"] = "running"
                    save_session(s)
                    return self.ok(s)
                if u.path == "/api/judge":
                    run_judge(s, load_config())
                    save_session(s)
                    return self.ok(s)
            return self.fail("Not found", 404)
        except json.JSONDecodeError as e:
            return self.fail(f"Invalid JSON: {e}")
        except Exception as e:
            return self.fail(e)


def main():
    if not os.path.exists(path("config.json")):
        save_config(load_config())
    if not os.path.exists(path("notebook.md")):
        write("notebook.md", "")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"Conscience by Conversation — {CREDIT}")
    print(f"Running at {url}   (Ctrl+C to stop)")
    print(f"Sessions are saved in {SESSIONS}")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
