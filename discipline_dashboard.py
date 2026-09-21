#!/usr/bin/env python3
"""Build the Daily Discipline morning reading.

The daily human question is the foundation. Public-domain authors supply the
readings; Claude selects and connects them without rewriting their words.
"""

import datetime
import html
import json
import os
import random
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic


HERE = Path(__file__).resolve().parent
OUTPUT_FILE = HERE / "index.html"
STATE_FILE = HERE / "run_state.json"
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"
MODEL_LABEL = "Claude Haiku 4.5"
TIMEZONE = ZoneInfo("America/Chicago")
EXCERPT_TARGET_CHARS = 1100
ECHO_TARGET_CHARS = 520
FRESHNESS_DAYS = 56
MAX_HISTORY_ENTRIES = 180

READING_SOURCES = [
    {
        "id": "tao", "file": HERE / "tao_te_ching_legge.json",
        "label": "Tao Te Ching", "sublabel": "home ground · one lead day in four",
        "attribution": "James Legge translation · 1891 · public domain",
        "title_prefix": "Chapter", "lead": True, "companion": True, "echo": True,
        "lead_chars": 5000,
        "voice": "Preserve non-forcing, humility, naturalness, paradox, and returning. Do not turn the Tao into passivity or generic calm.",
    },
    {
        "id": "chuangtzu", "file": HERE / "sources" / "chuangtzu.json",
        "label": "Chuang Tzu", "sublabel": "parable, freedom, and surprise",
        "attribution": "Herbert A. Giles translation · 1889 · public domain",
        "lead": True, "companion": True, "echo": True,
        "voice": "Preserve humor, story, reversal, and suspicion of rigid categories. Do not reduce Chuang Tzu to a restatement of the Tao Te Ching.",
    },
    {
        "id": "epictetus", "file": HERE / "sources" / "epictetus.json",
        "label": "Epictetus", "sublabel": "freedom at the boundary of choice",
        "attribution": "George Long translation · public domain",
        "lead": True, "companion": True, "echo": True,
        "voice": "Preserve judgment, desire, responsibility, and chosen response. Do not turn Epictetus into emotional suppression, hustle culture, or a generic Serenity Prayer.",
    },
    {
        "id": "brother_lawrence", "file": HERE / "sources" / "brother_lawrence.json",
        "label": "Brother Lawrence", "sublabel": "presence in ordinary things",
        "attribution": "The Practice of the Presence of God · 1895 edition · public domain",
        "lead": True, "companion": True, "echo": True,
        "voice": "Preserve explicitly Christian language of God, prayer, grace, love, and presence in ordinary work. Do not neutralize his faith into generic mindfulness.",
    },
    {
        "id": "heraclitus", "file": HERE / "sources" / "heraclitus.json",
        "label": "Heraclitus", "sublabel": "fire, tension, and hidden order",
        "attribution": "Fragments · John Burnet translation · public domain",
        "title_prefix": "Fragment", "lead": False, "companion": True, "echo": True,
        "voice": "Preserve tension, flux, opposition, and hidden order. Do not make Heraclitus sound gently Taoist.",
    },
]

ECHO_CANDIDATE_COUNT = {
    "tao": 4, "chuangtzu": 4, "epictetus": 5,
    "brother_lawrence": 4, "heraclitus": 8,
}
LINKS = {
    "aa_reflection": "https://www.aa.org/daily-reflections",
    "hazelden": "https://www.hazeldenbettyford.org/thought-for-the-day",
    "grapevine": "https://www.aagrapevine.org/#quote-of-the-day",
}


def log(message):
    timestamp = datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp}  {message}")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            state = json.load(handle)
        if isinstance(state, dict):
            state.setdefault("history", [])
            return state
    except Exception:
        pass
    return {"history": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")


def gate():
    now = datetime.datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    manual = os.environ.get("RUN_NOW") == "1"
    state = load_state()
    if not manual and state.get("date") == today and state.get("morning"):
        log(f"Already ran today ({today}). Exiting cleanly.")
        sys.exit(0)
    state["date"] = today
    state["morning"] = True
    save_state(state)
    log(f"Claimed today's slot ({today}, {'manual' if manual else 'scheduled'}); proceeding.")
    return state


def trim_to_excerpt(text, target=EXCERPT_TARGET_CHARS):
    if len(text) <= target:
        return text, False
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        return text[:target].rsplit(" ", 1)[0] + "…", True
    start = random.randrange(len(paragraphs))
    chunk, total, index = [paragraphs[start]], len(paragraphs[start]), start + 1
    while total < target and index < len(paragraphs):
        chunk.append(paragraphs[index])
        total += len(paragraphs[index])
        index += 1
    excerpt = "\n\n".join(chunk)
    if len(excerpt) > target:
        excerpt = excerpt[:target].rsplit(" ", 1)[0] + "…"
    return excerpt, True


def load_source(source):
    with open(source["file"], "r", encoding="utf-8") as handle:
        return json.load(handle)


def passage_from_entry(source, passage_id, entry, excerpt_target=None):
    if isinstance(entry, dict):
        passage_text, passage_title = entry.get("text", ""), entry.get("title")
    else:
        passage_text, passage_title = entry, None
    passage_text = re.sub(r"\[\d{1,3}\]", "", str(passage_text))
    passage_text = re.sub(r"[ \t]{2,}", " ", passage_text).strip()
    passage_text, excerpted = trim_to_excerpt(
        passage_text, excerpt_target or EXCERPT_TARGET_CHARS
    )
    if not passage_title and source.get("title_prefix"):
        passage_title = f"{source['title_prefix']} {passage_id}"
    if excerpted and passage_title:
        passage_title = f"{passage_title} · excerpt"
    return {
        "source": source, "passage_id": str(passage_id),
        "selection_key": f"{source['id']}:{passage_id}",
        "passage_title": passage_title or "Selected reading",
        "passage_text": passage_text,
    }


def balanced_source_order(available, day=None, salt="lead"):
    if not available:
        return []
    day = day or datetime.datetime.now(TIMEZONE).date()
    cycle, position = divmod(day.toordinal(), len(available))
    ordered = sorted(available, key=lambda source: source["id"])
    random.Random(f"{salt}:{cycle}").shuffle(ordered)
    return ordered[position:] + ordered[:position]


def recent_passage_ids(state, source_id, day=None):
    day = day or datetime.datetime.now(TIMEZONE).date()
    cutoff = day - datetime.timedelta(days=FRESHNESS_DAYS)
    recent = set()
    for entry in state.get("history", []):
        try:
            entry_date = datetime.date.fromisoformat(entry["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if entry_date < cutoff:
            continue
        for role in ("lead", "companion", "echo"):
            selection = str(entry.get(role, ""))
            prefix = f"{source_id}:"
            if selection.startswith(prefix):
                recent.add(selection[len(prefix):])
    return recent


def available_passage_ids(source, state, day=None):
    passages = load_source(source)
    all_ids = list(passages.keys())
    recent = recent_passage_ids(state, source["id"], day)
    fresh = [passage_id for passage_id in all_ids if str(passage_id) not in recent]
    return passages, fresh or all_ids


def pick_passage(source, state, excerpt_target=None, day=None):
    passages, passage_ids = available_passage_ids(source, state, day)
    if not passage_ids:
        return None
    passage_id = random.choice(passage_ids)
    return passage_from_entry(source, passage_id, passages[passage_id], excerpt_target)


def pick_lead(state, day=None):
    sources = [s for s in READING_SOURCES if s["lead"] and s["file"].exists()]
    for source in balanced_source_order(sources, day, "lead"):
        reading = pick_passage(source, state, source.get("lead_chars"), day)
        if reading:
            return reading


def pick_companion(lead, state, day=None):
    sources = [
        s for s in READING_SOURCES
        if s["companion"] and s["id"] != lead["source"]["id"] and s["file"].exists()
    ]
    for source in balanced_source_order(sources, day, "companion"):
        reading = pick_passage(source, state, EXCERPT_TARGET_CHARS, day)
        if reading:
            return reading


def pick_echo_candidates(lead, companion, state, day=None):
    excluded = {lead["source"]["id"], companion["source"]["id"]}
    candidates = []
    for source in READING_SOURCES:
        if source["id"] in excluded or not source["echo"] or not source["file"].exists():
            continue
        passages, passage_ids = available_passage_ids(source, state, day)
        count = min(ECHO_CANDIDATE_COUNT.get(source["id"], 4), len(passage_ids))
        for passage_id in random.sample(passage_ids, count):
            candidates.append(passage_from_entry(
                source, passage_id, passages[passage_id], ECHO_TARGET_CHARS
            ))
    return candidates


def resolve_echo_candidate(candidates, echo_key):
    raw_key = str(echo_key).strip()
    cleaned_key = re.sub(r"^key\s+", "", raw_key.strip("`'\""), flags=re.I).strip()

    def normalized(value):
        value = re.sub(r"^key\s+", "", str(value).strip().strip("`'\""), flags=re.I)
        return re.sub(r"\s+", "", value).rstrip(".,;").casefold()

    wanted = normalized(raw_key)
    matches = [c for c in candidates if normalized(c["selection_key"]) == wanted]
    if not matches:
        for candidate in candidates:
            key = candidate["selection_key"]
            if cleaned_key.casefold().startswith(key.casefold()):
                remainder = cleaned_key[len(key):].lstrip()
                if remainder.startswith(("—", "–", "-", ":", "(")):
                    matches.append(candidate)
    if len(matches) == 1:
        return matches[0]
    allowed = ", ".join(c["selection_key"] for c in candidates)
    raise ValueError(f"Unknown echo_key {raw_key!r}; expected one of: {allowed}")


def validate_editorial(result, echo_candidates):
    required = {
        "daily_question", "lead_lens", "companion_note", "echo_key",
        "echo_note", "confluence", "carry_question",
    }
    missing = required.difference(result)
    if missing:
        raise ValueError(f"Editorial response missing keys: {', '.join(sorted(missing))}")
    for key in required:
        if not isinstance(result[key], str) or not result[key].strip():
            raise ValueError(f"Editorial field {key!r} is empty or not text.")
    for key in ("daily_question", "carry_question"):
        words = result[key].split()
        if not result[key].strip().endswith("?") or not 6 <= len(words) <= 40:
            raise ValueError(f"Editorial field {key!r} must be a focused 6-40 word question.")
    return result, resolve_echo_candidate(echo_candidates, result["echo_key"])


def create_editorial(client, lead, companion, echo_candidates):
    candidates = "\n\n---\n\n".join(
        f"KEY {c['selection_key']} — {c['source']['label']} — {c['passage_title']}:\n{c['passage_text']}"
        for c in echo_candidates
    )
    prompt = f"""You are the restrained editor of Daily Discipline, a private morning practice for one person active in AA recovery and interested in spiritual growth, love, kindness, courage, surrender, and living in conscious relationship with God and the unfolding universe.

The public-domain readings below are the authors' voices. Do not rewrite them, imitate them, or make them agree. Your work is limited to selecting one bounded echo and writing brief connective editorial material.

TODAY'S LEAD — {lead['source']['label']} ({lead['passage_title']}):
[BEGIN LEAD READING]
{lead['passage_text']}
[END LEAD READING]
Voice integrity: {lead['source']['voice']}

TODAY'S FULL COMPANION — {companion['source']['label']} ({companion['passage_title']}):
[BEGIN COMPANION READING]
{companion['passage_text']}
[END COMPANION READING]
Voice integrity: {companion['source']['voice']}

Choose one SHORT echo from these exact candidates. Choose genuine resonance or productive tension with both readings. The third voice must add something distinct, not decorative agreement.

{candidates}

Return ONLY a JSON object, without markdown fences, using exactly these keys:
{{
  "daily_question": "A challenging first-person question, 12-28 words, arising from the lead and carried into the day. Interrupt fear, worry, or anxious narrowing and invite movement toward presence, trust, sobriety, growth, love, kindness, service, courage, God, or openness to life's unfolding. Emphasize only what fits today; never list all values, shame, preach, promise fear will vanish, or use a motivational cliché.",
  "lead_lens": "One 80-110 word paragraph opening the lead in plain language and bringing it into contemporary lived experience without replacing the source.",
  "companion_note": "One 45-75 word paragraph explaining what the companion adds, corrects, or challenges on its own terms.",
  "echo_key": "The exact source:passage KEY of the strongest echo candidate.",
  "echo_note": "One or two concise sentences naming why this exact echo belongs and what tension or resonance it introduces.",
  "confluence": "One 80-120 word paragraph naming both where the three voices meet and where they meaningfully differ. Do not flatten them into one philosophy.",
  "carry_question": "A distinct first-person question, 10-24 words, for the next fearful, uncertain, or ordinary moment today. Invite one honest or loving action instead of more rumination."
}}

The question should open a door, not become another problem to solve before breakfast. Write with warmth, spiritual seriousness, and economy. Share, do not preach."""
    message = client.messages.create(
        model=MODEL, max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in message.content if hasattr(b, "text")).strip()
    return json.loads(text.replace("```json", "").replace("```", "").strip())


def esc(value):
    return html.escape(str(value), quote=True)


def reading_paragraphs(reading):
    return "".join(
        f"<p>{esc(paragraph)}</p>"
        for paragraph in reading["passage_text"].split("\n\n") if paragraph.strip()
    )


def build_reading_html(reading, number, role, note_label, note):
    source = reading["source"]
    return f"""
  <section class="reading" aria-labelledby="reading-{number}">
    <div class="eyebrow">{number} · {esc(role)} · {esc(source['label'])}</div>
    <h2 id="reading-{number}">{esc(reading['passage_title'])}</h2>
    <div class="source-note">{esc(source['attribution'])}</div>
    <div class="verse">{reading_paragraphs(reading)}</div>
    <div class="movement"><h3>{esc(note_label)}</h3><p>{esc(note)}</p></div>
  </section>"""


def build_echo_html(echo, editorial):
    source = echo["source"]
    return f"""
  <section class="echo" aria-labelledby="echo-heading">
    <div class="eyebrow">04 · The Echo · {esc(source['label'])}</div>
    <h2 id="echo-heading">{esc(echo['passage_title'])}</h2>
    <div class="source-note">{esc(source['attribution'])}</div>
    <div class="verse">{reading_paragraphs(echo)}</div>
    <p class="echo-note">{esc(editorial['echo_note'])}</p>
  </section>"""


def build_html(lead, companion, echo, editorial):
    now = datetime.datetime.now(TIMEZONE)
    date_string = f"{now:%A, %B} {now.day}, {now:%Y}"
    lead_html = build_reading_html(
        lead, "02", "Today's lead", "A lens for today", editorial["lead_lens"]
    )
    companion_html = build_reading_html(
        companion, "03", "The companion", "What this voice adds",
        editorial["companion_note"],
    )
    echo_html = build_echo_html(echo, editorial)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="description" content="Daily Discipline: recovery, spiritual reading, and one question to carry into the day.">
<title>Daily Discipline — {date_string}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..700;1,9..144,300..600&amp;family=Inter+Tight:wght@300;400;500;600&amp;family=JetBrains+Mono:wght@400;500;600&amp;display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}:root{{--paper:#100E17;--paper2:#171421;--line:#332C3D;--ink:#F0EDE8;--dim:#B8B1C3;--faint:#81798E;--brass:#C4956A;--bright:#E0B47F;--display:"Fraunces",Georgia,serif;--body:"Inter Tight",system-ui,sans-serif;--mono:"JetBrains Mono",monospace}}
body{{background:radial-gradient(circle at 84% 8%,rgba(196,149,106,.09),transparent 30rem),radial-gradient(circle at 10% 58%,rgba(122,158,138,.07),transparent 34rem),var(--paper);color:var(--ink);font-family:var(--body);line-height:1.65;-webkit-font-smoothing:antialiased;padding-bottom:60px}}a{{color:inherit;text-decoration:none}}.wrap{{max-width:820px;margin:auto;padding:0 28px}}
.topnav{{display:flex;align-items:center;justify-content:space-between;padding:16px 0;border-bottom:1px solid var(--line)}}.home{{font-family:var(--mono);font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim)}}.home span{{color:var(--brass);font-weight:600}}.here{{font-family:var(--display);font-style:italic;font-size:14px;color:var(--dim)}}
.top{{padding:56px 0 28px;border-bottom:1px solid var(--line);margin-bottom:34px}}.kicker,.eyebrow,.movement h3,.question-card .label{{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--brass)}}.kicker{{margin-bottom:14px}}.top h1{{font-family:var(--display);font-weight:330;font-size:clamp(38px,6vw,58px);letter-spacing:-.03em;line-height:1.02}}.date{{font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--dim);margin-top:14px;text-transform:uppercase}}
.open-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:54px}}.card-link{{border:1px solid var(--line);padding:16px;transition:.2s;background:rgba(255,255,255,.025);min-height:92px}}.card-link:hover{{border-color:var(--brass);background:var(--paper2);transform:translateY(-1px)}}.card-link .label{{font-family:var(--mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--brass);margin-bottom:6px}}.card-link h2{{font-family:var(--display);font-weight:400;font-size:17px;line-height:1.2}}.go{{font-family:var(--mono);font-size:10px;color:var(--faint);margin-top:8px}}
.question-card{{margin-bottom:72px;padding:34px 36px 36px;border-block:1px solid rgba(196,149,106,.45);background:linear-gradient(105deg,rgba(196,149,106,.08),transparent 65%)}}.question-card .label{{margin-bottom:13px}}.question-card h2{{font-family:var(--display);font-weight:350;font-size:clamp(31px,5vw,48px);letter-spacing:-.02em;line-height:1.18}}
.reading{{margin-top:72px;padding-top:58px;border-top:1px solid var(--line)}}.eyebrow{{margin-bottom:10px}}.reading h2,.echo h2{{font-family:var(--display);font-weight:350;font-size:clamp(28px,4vw,42px);line-height:1.15;margin-bottom:8px}}.source-note{{font-family:var(--mono);font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);margin-bottom:24px}}.verse{{border-left:2px solid var(--brass);padding:4px 0 4px 26px;margin-bottom:30px}}.verse p{{font-family:var(--display);font-weight:300;font-size:19px;line-height:1.72;margin-bottom:1rem}}.verse p:last-child{{margin-bottom:0}}.movement{{padding:25px 27px;background:var(--paper2);border:1px solid var(--line)}}.movement h3{{margin-bottom:11px}}.movement p{{font-size:16.5px;line-height:1.72}}
.echo{{margin-top:72px;padding:34px;border:1px solid rgba(196,149,106,.38);background:linear-gradient(135deg,rgba(196,149,106,.07),rgba(255,255,255,.02))}}.echo .verse{{margin-bottom:20px}}.echo .verse p{{font-size:21px}}.echo-note{{font-size:15.5px;line-height:1.7;color:var(--dim)}}.confluence{{margin-top:72px;padding-top:58px;border-top:1px solid var(--brass)}}.confluence h2{{font-family:var(--display);font-weight:350;font-size:clamp(34px,5vw,48px);line-height:1.1;margin-bottom:22px}}.confluence>p{{font-size:17px;line-height:1.75}}.carry{{margin-top:28px;padding:28px;background:var(--paper2);border:1px solid rgba(196,149,106,.35)}}.carry .label{{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--brass);margin-bottom:10px}}.carry p:last-child{{font-family:var(--display);font-style:italic;font-size:21px;line-height:1.55}}
footer{{margin-top:70px;padding-top:30px;border-top:1px solid var(--line);font-family:var(--mono);font-size:10px;letter-spacing:.04em;color:var(--dim);line-height:1.75}}footer p{{margin-bottom:10px}}footer strong{{color:var(--bright);font-weight:500}}@media(max-width:680px){{.wrap{{padding:0 18px}}.open-grid{{grid-template-columns:1fr}}.card-link{{min-height:0}}.question-card{{padding:28px 22px 30px}}.reading{{margin-top:58px;padding-top:46px}}.verse{{padding-left:20px}}.echo{{padding:27px 22px}}}}
</style></head><body><div class="wrap">
<nav class="topnav" aria-label="Site navigation"><a class="home" href="https://jdb-builds.com"><span>JDB</span> · Home</a><span class="here">Daily Discipline</span></nav>
<header class="top"><div class="kicker">One question · rotating voices · one day at a time</div><h1>Every 24 Hours,<br>Begin Again.</h1><div class="date">{date_string}</div></header>
<nav class="open-grid" aria-label="Recovery readings">
<a class="card-link" href="{LINKS['aa_reflection']}" target="_blank" rel="noopener"><div class="label">Alcoholics Anonymous</div><h2>Daily Reflection</h2><div class="go">Open ↗</div></a>
<a class="card-link" href="{LINKS['hazelden']}" target="_blank" rel="noopener"><div class="label">Hazelden Betty Ford</div><h2>Twenty-Four Hours</h2><div class="go">Open ↗</div></a>
<a class="card-link" href="{LINKS['grapevine']}" target="_blank" rel="noopener"><div class="label">AA Grapevine</div><h2>Quote of the Day</h2><div class="go">Open ↗</div></a></nav>
<section class="question-card" aria-labelledby="daily-question"><div class="label">01 · The question</div><h2 id="daily-question">{esc(editorial['daily_question'])}</h2></section>
{lead_html}
{companion_html}
{echo_html}
<section class="confluence" aria-labelledby="confluence-heading"><div class="eyebrow">05 · The Confluence</div><h2 id="confluence-heading">Where they meet.<br>Where they part.</h2><p>{esc(editorial['confluence'])}</p><div class="carry"><div class="label">Take this into the day</div><p>{esc(editorial['carry_question'])}</p></div></section>
<footer>
<p><strong>What is pulled:</strong> three bounded readings from a local public-domain library: Tao Te Ching (James Legge, 1891), Chuang Tzu (Herbert A. Giles, 1889), Epictetus (George Long), Brother Lawrence's <em>The Practice of the Presence of God</em> (1895 edition), and Heraclitus fragments (John Burnet). Daily Reflection, Twenty-Four Hours, and Grapevine remain links to their publishers.</p>
<p><strong>How the rotation works:</strong> the Tao leads 25% of days. Chuang Tzu, Epictetus, and Brother Lawrence share the other lead days equally. Heraclitus usually serves as a concise echo. Recent selections are excluded for 56 days when unused material remains.</p>
<p><strong>How AI is used:</strong> Anthropic {MODEL_LABEL} (<code>{MODEL}</code>) receives only today's bounded candidate readings. It selects the echo and writes the daily question, brief lens, companion note, Confluence, and carry question. AI does not write, paraphrase, or alter the source readings.</p>
<p>Daily Discipline · jdb-builds.com · generated fresh each morning</p>
</footer></div></body></html>"""


def record_history(state, lead, companion, echo):
    today = datetime.datetime.now(TIMEZONE).date()
    history = list(state.get("history", []))
    history.append({
        "date": today.isoformat(), "lead": lead["selection_key"],
        "companion": companion["selection_key"], "echo": echo["selection_key"],
    })
    cutoff = today - datetime.timedelta(days=MAX_HISTORY_ENTRIES)
    retained = []
    for entry in history:
        try:
            if datetime.date.fromisoformat(entry["date"]) >= cutoff:
                retained.append(entry)
        except (KeyError, TypeError, ValueError):
            continue
    state["history"] = retained[-MAX_HISTORY_ENTRIES:]
    save_state(state)


def main():
    state = gate()
    log("── Daily Discipline Generator ──")
    if not API_KEY:
        log("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    missing = [s["file"].name for s in READING_SOURCES if not s["file"].exists()]
    if missing:
        log(f"ERROR: Missing source files: {', '.join(missing)}")
        sys.exit(1)

    day = datetime.datetime.now(TIMEZONE).date()
    lead = pick_lead(state, day)
    if not lead:
        log("ERROR: No lead reading available; keeping the last complete page.")
        sys.exit(1)
    log(f"Lead: {lead['source']['label']} — {lead['passage_id']}")

    companion = pick_companion(lead, state, day)
    if not companion:
        log("ERROR: No companion reading available; keeping the last complete page.")
        sys.exit(1)
    log(f"Companion: {companion['source']['label']} — {companion['passage_id']}")

    echo_candidates = pick_echo_candidates(lead, companion, state, day)
    if not echo_candidates:
        log("ERROR: No echo candidates available; keeping the last complete page.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=API_KEY)
    for attempt in range(1, 3):
        try:
            log(f"Creating bounded editorial with {MODEL_LABEL} (attempt {attempt})...")
            editorial, echo = validate_editorial(
                create_editorial(client, lead, companion, echo_candidates),
                echo_candidates,
            )
            break
        except Exception as error:
            if attempt == 1:
                log(f"Editorial attempt 1 failed ({error}); retrying once.")
            else:
                log(f"ERROR: Editorial generation failed twice; keeping the last complete page. Final error: {error}")
                sys.exit(1)

    log(f"Echo: {echo['source']['label']} — {echo['passage_id']}")
    temporary = OUTPUT_FILE.with_suffix(".html.tmp")
    temporary.write_text(build_html(lead, companion, echo, editorial), encoding="utf-8")
    temporary.replace(OUTPUT_FILE)
    record_history(state, lead, companion, echo)
    log(f"Built dashboard -> {OUTPUT_FILE}")
    log("Running in GitHub Actions; workflow handles push." if os.environ.get("GITHUB_ACTIONS") == "true" else "Local run complete. Commit and push when ready.")
    log("Done.")


if __name__ == "__main__":
    main()
