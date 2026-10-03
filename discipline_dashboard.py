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
PRACTICE_DEFAULTS = {
    "surrender_question": "What outcome can I entrust to God today while remaining available for the next honest action?",
    "daily_action": "Before one difficult moment today, I will pause, entrust the outcome to God, and take one kind or honest step.",
    "evening_question": "Where did I loosen my grip today, and what am I still willing to entrust to God?",
}

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
        "id": "psalms", "file": HERE / "sources" / "psalms.json",
        "label": "Psalms", "sublabel": "prayer, lament, gratitude, and trust",
        "attribution": "King James Version · public domain in the USA",
        "lead": False, "companion": True, "echo": True,
        "voice": "Preserve the Psalms as ancient Israel's prayers and songs, received in Jewish and Christian traditions: direct address to God, lament, praise, fear, gratitude, anger, and trust. Allow unresolved grief and difficult language about judgment or enemies. Do not turn prayer into generic mindfulness, equate God with the Tao, prescribe retaliation, or promise safety or success.",
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
    "brother_lawrence": 4, "psalms": 8, "heraclitus": 8,
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


def psalm_excerpt(entry, target):
    """Choose a contiguous verse group; never cut a prayer mid-verse."""
    groups, current, length = [], [], 0
    for verse in entry["verses"]:
        verse_length = len(verse["text"])
        if current and length + 2 + verse_length > target:
            groups.append(current)
            current, length = [], 0
        current.append(verse)
        length += verse_length + (2 if len(current) > 1 else 0)
    if current:
        groups.append(current)
    selected = random.choice(groups)
    title = entry["title"]
    if len(groups) > 1:
        first, last = selected[0]["number"], selected[-1]["number"]
        verse_range = str(first) if first == last else f"{first}–{last}"
        title += f":{verse_range} · excerpt"
    return "\n\n".join(verse["text"] for verse in selected), title


def passage_from_entry(source, passage_id, entry, excerpt_target=None):
    if source["id"] == "psalms":
        passage_text, passage_title = psalm_excerpt(entry, excerpt_target or EXCERPT_TARGET_CHARS)
        return {
            "source": source, "passage_id": str(passage_id),
            "selection_key": f"{source['id']}:{passage_id}",
            "passage_title": passage_title, "passage_text": passage_text,
        }
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
    day = day or datetime.datetime.now(TIMEZONE).date()
    sources = [
        s for s in READING_SOURCES
        if s["companion"] and s["id"] != lead["source"]["id"] and s["file"].exists()
    ]
    psalms = [source for source in sources if source["id"] == "psalms"]
    others = [source for source in sources if source["id"] != "psalms"]
    # Half of calendar days guarantee a Psalms companion. On the other days
    # it remains available to the editor as an Echo, alongside other voices.
    ordered = balanced_source_order(others, day, "companion")
    if day.toordinal() % 2 == 0:
        ordered = psalms + ordered
    for source in ordered:
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
    # These new short prompts must not invalidate an otherwise complete reading.
    # Fixed editorial defaults keep the practice usable if a field is omitted,
    # malformed, or too long; the existing reading validation stays strict.
    for key, fallback in PRACTICE_DEFAULTS.items():
        value = result.get(key)
        valid = isinstance(value, str) and 6 <= len(value.split()) <= 40
        if key.endswith("question"):
            valid = valid and value.strip().endswith("?")
        if not valid:
            result[key] = fallback
            log(f"Using fixed editorial default for {key}.")
        else:
            result[key] = value.strip()
    return result, resolve_echo_candidate(echo_candidates, result["echo_key"])


def create_editorial(client, lead, companion, echo_candidates):
    candidates = "\n\n---\n\n".join(
        f"KEY {c['selection_key']} — {c['source']['label']} — {c['passage_title']}:\n{c['passage_text']}"
        for c in echo_candidates
    )
    echo_sources = {candidate["source"]["id"]: candidate["source"] for candidate in echo_candidates}
    echo_voices = "\n".join(f"{source['label']}: {source['voice']}" for source in echo_sources.values())
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

Echo voice integrity:
{echo_voices}

{candidates}

Return ONLY a JSON object, without markdown fences, using exactly these keys:
{{
  "daily_question": "A challenging first-person question, 12-28 words, arising from the lead and carried into the day. Interrupt fear, worry, or anxious narrowing and invite movement toward presence, trust, sobriety, growth, love, kindness, service, courage, God, or openness to life's unfolding. Emphasize only what fits today; never list all values, shame, preach, promise fear will vanish, or use a motivational cliché.",
  "lead_lens": "One 80-110 word paragraph opening the lead in plain language and bringing it into contemporary lived experience without replacing the source.",
  "companion_note": "One 45-75 word paragraph explaining what the companion adds, corrects, or challenges on its own terms.",
  "echo_key": "The exact source:passage KEY of the strongest echo candidate.",
  "echo_note": "One or two concise sentences naming why this exact echo belongs and what tension or resonance it introduces.",
  "confluence": "One 80-120 word paragraph naming both where the three voices meet and where they meaningfully differ. Do not flatten them into one philosophy.",
  "carry_question": "NOTICE: A distinct first-person question, 10-24 words, helping me recognize fear, grasping, avoidance, or a chance for love in an ordinary moment today. Keep it grounded in these readings.",
  "surrender_question": "SURRENDER: One first-person question, 10-24 words, naming a particular outcome, demand for certainty, or urge to control I can entrust to God today while staying present and responsible. Preserve the readings' distinct beliefs; do not claim every author means God in the same way.",
  "daily_action": "ACT: One concrete, modest first-person commitment, 12-28 words, I can carry out today in kindness, sobriety, courage, service, or honest attention. Make it specific enough to try in an ordinary encounter and connected to these readings.",
  "evening_question": "One gentle but honest first-person question, 12-28 words, returning tonight to today's practice: where did I loosen my grip, act with love, or remain afraid, and what can I entrust to God now? Choose one or two threads, not a checklist or score."
}}

Surrender means releasing my demand to control outcomes while remaining willing to participate in life. Do not equate it with giving up, avoiding responsibility, accepting harm, dropping boundaries, or neglecting sobriety. Do not promise that prayer removes fear or guarantees an outcome. Let love, kindness, growth, and openness emerge where the reading supports them; do not force every theme into every field.

The question should open a door, not become another problem to solve before breakfast. Write with warmth, spiritual seriousness, and economy. Share, do not preach. Use plain text only; no Markdown emphasis inside JSON strings."""
    message = client.messages.create(
        model=MODEL, max_tokens=1800,
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


def history_entry(lead, companion, echo, editorial=None, day=None):
    day = day or datetime.datetime.now(TIMEZONE).date()
    entry = {"date": day.isoformat()}
    for role, reading in (("lead", lead), ("companion", companion), ("echo", echo)):
        entry[role] = reading["selection_key"]
        entry[f"{role}_title"] = reading["passage_title"]
    if editorial:
        for key in ("daily_question", "carry_question", *PRACTICE_DEFAULTS):
            entry[key] = editorial.get(key, PRACTICE_DEFAULTS.get(key, ""))
    return entry


def seven_day_trail(history, day=None):
    day = day or datetime.datetime.now(TIMEZONE).date()
    cutoff = day - datetime.timedelta(days=6)
    dates = {}
    for entry in history:
        try:
            entry_day = datetime.date.fromisoformat(entry["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if cutoff <= entry_day <= day:
            dates[entry_day] = entry  # Manual reruns show only the latest entry for a date.
    return [dates[entry_day] for entry_day in sorted(dates, reverse=True)]


def build_evening_html(date, question, suffix="today"):
    return f"""<div class="evening-entry" data-note-date="{esc(date)}">
<p class="night-question">{esc(question)}</p>
<div class="private-note" hidden>
<label for="evening-note-{esc(suffix)}">A few words to return to (optional)</label>
<textarea id="evening-note-{esc(suffix)}" rows="4" maxlength="4000" autocomplete="off" spellcheck="false" placeholder="What can I entrust to God tonight?"></textarea>
<p class="note-privacy">Saved only in this browser on this device. No account or cloud sync. Clearing browser data removes saved notes.</p>
<div class="note-actions"><button type="button" data-note-save>Save on this device</button><button type="button" data-note-clear>Clear this note</button></div>
<p class="note-status" role="status" aria-live="polite"></p></div>
<noscript><p class="note-privacy">You can reflect on this question here; saving a note requires JavaScript.</p></noscript>
</div>"""


def build_trail_html(entries, day):
    sources = {source["id"]: source for source in READING_SOURCES}
    rendered = []
    for entry in seven_day_trail(entries, day):
        date = entry["date"]
        entry_day = datetime.date.fromisoformat(date)
        voices = []
        for role in ("lead", "companion", "echo"):
            source_id, _, passage_id = str(entry.get(role, "")).partition(":")
            source = sources.get(source_id)
            if source:
                title = entry.get(f"{role}_title") or f"Reading {passage_id}"
                voices.append(f"{role.title()}: {source['label']} · {title}")
        content = f'<p class="trail-voices">{esc(" / ".join(voices))}</p>'
        if entry.get("daily_question"):
            content += f'<p class="trail-question">{esc(entry["daily_question"])}</p>'
            content += build_practice_html(entry, compact=True)
            if entry.get("evening_question"):
                content += build_evening_html(date, entry["evening_question"], date)
        else:
            content += '<p class="trail-empty">Reading selections are available. Practice prompts were not saved before this update.</p>'
        rendered.append(f'<li><details><summary><time datetime="{esc(date)}">{entry_day:%A, %B} {entry_day.day}</time></summary><div class="trail-content">{content}</div></details></li>')
    return '<ul class="trail-list">' + "".join(rendered) + '</ul>'


def build_practice_html(editorial, compact=False):
    steps = "".join(
        f'<div><dt>{label}</dt><dd>{esc(editorial.get(key, PRACTICE_DEFAULTS.get(key, "")))}</dd></div>'
        for label, key in (("Notice", "carry_question"), ("Surrender", "surrender_question"), ("Act", "daily_action"))
    )
    if compact:
        return f'<dl class="practice-steps compact">{steps}</dl>'
    return f'<section class="carry" aria-labelledby="practice-heading"><h3 id="practice-heading">Into the Day</h3><dl class="practice-steps">{steps}</dl></section>'


def build_html(lead, companion, echo, editorial, state=None, day=None):
    day = day or datetime.datetime.now(TIMEZONE).date()
    date_string = f"{day:%A, %B} {day.day}, {day:%Y}"
    lead_html = build_reading_html(
        lead, "02", "Today's lead", "A lens for today", editorial["lead_lens"]
    )
    companion_html = build_reading_html(
        companion, "03", "The companion", "What this voice adds",
        editorial["companion_note"],
    )
    echo_html = build_echo_html(echo, editorial)
    practice_html = build_practice_html(editorial)
    evening_html = build_evening_html(day.isoformat(), editorial.get("evening_question", PRACTICE_DEFAULTS["evening_question"]))
    entries = list((state or {}).get("history", [])) + [history_entry(lead, companion, echo, editorial, day)]
    trail_html = build_trail_html(entries, day)
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
.carry h3{{font-family:var(--mono);font-size:12px;font-weight:500;letter-spacing:.16em;text-transform:uppercase;color:var(--brass);margin-bottom:22px}}.practice-steps{{display:grid;gap:20px}}.practice-steps>div{{display:grid;grid-template-columns:100px 1fr;gap:16px}}.practice-steps dt{{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--bright);padding-top:6px}}.practice-steps dd{{font-family:var(--display);font-size:21px;line-height:1.5;overflow-wrap:anywhere}}.practice-steps.compact{{margin:20px 0}}.practice-steps.compact dd{{font-size:18px}}
.return,.trail{{margin-top:26px;border-block:1px solid var(--line)}}summary{{padding:22px 0;cursor:pointer;color:var(--bright);font-family:var(--display);font-size:23px;line-height:1.3}}summary::marker{{color:var(--brass)}}summary small{{display:block;color:var(--dim);font-family:var(--body);font-size:14px;font-weight:400;line-height:1.5;margin:8px 0 0 20px}}.evening-entry{{padding:0 0 24px}}.night-question{{font-family:var(--display);font-size:22px;line-height:1.5;margin-bottom:22px}}.private-note label{{display:block;font-size:15px;margin-bottom:10px}}textarea{{width:100%;resize:vertical;background:var(--paper2);border:1px solid var(--line);color:var(--ink);font:16px/1.6 var(--body);padding:16px;min-height:120px;border-radius:2px}}.note-privacy,.note-status,.trail-empty{{font-size:13px;color:var(--dim);line-height:1.6;margin-top:10px}}.note-actions{{display:flex;flex-wrap:wrap;gap:10px;margin-top:15px}}.note-actions button{{min-height:44px;padding:10px 15px;background:var(--paper2);border:1px solid var(--line);border-radius:2px;color:var(--ink);font:14px var(--body);cursor:pointer}}.note-actions button:hover{{border-color:var(--brass)}}:focus-visible{{outline:2px solid var(--bright);outline-offset:4px}}.trail-intro{{font-size:14px;color:var(--dim);margin-bottom:16px}}.trail-list{{list-style:none}}.trail-list>li{{border-top:1px solid var(--line)}}.trail-list summary{{font:16px/1.5 var(--body);padding:17px 0}}.trail-content{{padding-bottom:22px}}.trail-voices{{font-family:var(--mono);font-size:11px;line-height:1.8;color:var(--dim);overflow-wrap:anywhere}}.trail-question{{font-family:var(--display);font-size:22px;line-height:1.5;margin-top:16px}}[hidden]{{display:none!important}}
footer{{margin-top:70px;padding-top:30px;border-top:1px solid var(--line);font-family:var(--mono);font-size:10px;letter-spacing:.04em;color:var(--dim);line-height:1.75}}footer p{{margin-bottom:10px}}footer strong{{color:var(--bright);font-weight:500}}@media(max-width:680px){{.wrap{{padding:0 18px}}.open-grid{{grid-template-columns:1fr}}.card-link{{min-height:0}}.question-card{{padding:28px 22px 30px}}.reading{{margin-top:58px;padding-top:46px}}.verse{{padding-left:20px}}.echo{{padding:27px 22px}}.carry{{padding:24px 22px}}.practice-steps>div{{grid-template-columns:1fr;gap:5px}}.practice-steps dt{{padding-top:0}}}}
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
<section class="confluence" aria-labelledby="confluence-heading"><div class="eyebrow">05 · The Confluence</div><h2 id="confluence-heading">Where they meet.<br>Where they part.</h2><p>{esc(editorial['confluence'])}</p></section>
{practice_html}
<details class="return"><summary>Return Tonight<small>A moment to notice, give thanks, and surrender what remains.</small></summary>{evening_html}</details>
<details class="trail"><summary>Seven-Day Trail<small>Return to a question, a voice, or a small act of willingness.</small></summary><p class="trail-intro">The past seven calendar days, newest first. Each day holds its latest generated reading; new practice prompts collect from this update onward.</p>{trail_html}</details>
<footer>
<p><strong>What is pulled:</strong> three bounded readings from a local public-domain library: Tao Te Ching (James Legge, 1891), Chuang Tzu (Herbert A. Giles, 1889), Epictetus (George Long), Brother Lawrence's <em>The Practice of the Presence of God</em> (1895 edition), <a href="https://www.gutenberg.org/ebooks/10">Psalms (King James Version, public domain in the USA)</a>, and Heraclitus fragments (John Burnet). Psalms draws from all 150 prayers and songs; longer readings use contiguous, complete verses with the range shown. Daily Reflection, Twenty-Four Hours, and Grapevine remain links to their publishers.</p>
<p><strong>How the rotation works:</strong> the Tao leads 25% of days. Chuang Tzu, Epictetus, and Brother Lawrence share the other lead days equally. Psalms is the companion every other day and is available as an Echo on the remaining days. Heraclitus can appear as a companion or Echo. Recent selections are excluded for 56 days when unused material remains; selecting any excerpt of a Psalm counts as selecting that whole Psalm.</p>
<p><strong>How AI is used:</strong> Anthropic {MODEL_LABEL} (<code>{MODEL}</code>) receives only today's bounded candidate readings. It selects the echo and writes the daily question, brief lens, companion note, Confluence, Notice question, Surrender question, daily action, and evening reflection. Brief practice prompts may use fixed editorial defaults when needed. AI does not write, paraphrase, or alter the source readings. Your evening notes stay in this browser and are never sent to the generator or AI.</p>
<p>Daily Discipline · jdb-builds.com · generated fresh each morning</p>
</footer></div><script src="practice.js" defer></script></body></html>"""


def record_history(state, lead, companion, echo, editorial=None, day=None):
    today = day or datetime.datetime.now(TIMEZONE).date()
    history = list(state.get("history", []))
    history.append(history_entry(lead, companion, echo, editorial, today))
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
    temporary.write_text(build_html(lead, companion, echo, editorial, state, day), encoding="utf-8")
    temporary.replace(OUTPUT_FILE)
    record_history(state, lead, companion, echo, editorial, day)
    log(f"Built dashboard -> {OUTPUT_FILE}")
    log("Running in GitHub Actions; workflow handles push." if os.environ.get("GITHUB_ACTIONS") == "true" else "Local run complete. Commit and push when ready.")
    log("Done.")


if __name__ == "__main__":
    main()
