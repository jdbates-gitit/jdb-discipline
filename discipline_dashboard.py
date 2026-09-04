#!/usr/bin/env python3
# discipline_dashboard.py
# Daily Discipline — a morning contemplative dashboard.
#
# Four sections:
#   1. Daily Reflection (AA)      -> launchpad card linking to aa.org
#   2. Twenty-Four Hours a Day    -> launchpad card linking to Hazelden
#   3. Grapevine Quote of the Day -> launchpad card linking to AA Grapevine
#   4. Daily philosophical dialogue -> Tao Te Ching as the anchor, one full
#        companion reading, a short thematically chosen echo from the other
#        author, and a closing synthesis called The Confluence.
#
# Reads Legge text ONLY from local tao_te_ching_legge.json (no outside source).
# The first scheduled run each day claims the date; later retries exit cleanly.

import os
import re
import sys
import json
import random
import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
TAO_FILE = HERE / "tao_te_ching_legge.json"
OUTPUT_FILE = HERE / "index.html"
STATE_FILE = HERE / "run_state.json"
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Companion-text sources. Pluggable: add a new dict here (id, file, label,
# relationship) and it's picked up automatically -- no other code changes
# needed. "relationship" controls how the Claude prompt frames the day's
# pairing against the Tao chapter:
#   complement  -- same lineage, different mode (e.g. story vs. aphorism)
#   convergence -- independent tradition, same insight anyway
#   counterweight -- practical agency set against acceptance and non-forcing
#   opposite    -- opposite prescription, same underlying diagnosis
COMPANION_SOURCES = [
    {
        "id": "chuangtzu",
        "file": HERE / "sources" / "chuangtzu.json",
        "label": "Chuang Tzu",
        "sublabel": "same root, different voice",
        "relationship": "complement",
    },
    {
        "id": "heraclitus",
        "file": HERE / "sources" / "heraclitus.json",
        "label": "Heraclitus",
        "sublabel": "no contact, same mountain",
        "relationship": "convergence",
    },
    {
        "id": "epictetus",
        "file": HERE / "sources" / "epictetus.json",
        "label": "Epictetus",
        "sublabel": "freedom at the boundary of choice",
        "relationship": "counterweight",
    },
]

# Launchpad sources (we link, never reproduce — these are copyrighted)
LINKS = {
    "aa_reflection": "https://www.aa.org/daily-reflections",
    "hazelden": "https://www.hazeldenbettyford.org/thought-for-the-day",
    "grapevine": "https://www.aagrapevine.org/#quote-of-the-day",
}


def log(msg):
    ts = datetime.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts}  {msg}")


# ---------------------------------------------------------------------------
# First-run-of-the-day gate. Scheduled runs may arrive late, so the date in
# run_state.json -- not the wall clock -- decides whether work is needed.
# ---------------------------------------------------------------------------
def gate():
    if os.environ.get("RUN_NOW") == "1":
        return
    now = datetime.datetime.now(ZoneInfo("America/Chicago"))
    today = now.strftime("%Y-%m-%d")
    state = {"date": today, "morning": False}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if loaded.get("date") == today:
            state = loaded
    except Exception:
        pass
    if state.get("morning"):
        log(f"Already ran today ({today}). Exiting cleanly.")
        sys.exit(0)
    state["date"] = today
    state["morning"] = True
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
        log(f"Claimed today's slot ({today}); proceeding.")
    except Exception as e:
        log(f"Could not write run_state.json: {e}")


# ---------------------------------------------------------------------------
# Tao chapter selection + Claude reflection
# ---------------------------------------------------------------------------
def load_tao():
    with open(TAO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_chapter(tao):
    # Pure random draw -- every run picks a fresh chapter. The windowed run gate
    # ensures only one scheduled run does work per day; manual re-runs (RUN_NOW=1)
    # intentionally draw a new chapter each time, for when you want more Tao.
    num = str(random.randint(1, 81))
    return num, tao[num]


# ---------------------------------------------------------------------------
# Companion text selection + Claude reflection
# ---------------------------------------------------------------------------
def passage_from_entry(source, passage_id, entry, excerpt_target=None):
    # Support both the {id: "text"} shape (Heraclitus) and the
    # {id: {"title":..., "text":...}} shape (Chuang Tzu chapters).
    if isinstance(entry, dict):
        passage_text = entry.get("text", "")
        passage_title = entry.get("title")
    else:
        passage_text = entry
        passage_title = None

    # Strip stray footnote reference markers (e.g. "[441]") left over
    # from the Gutenberg source's <sup> footnote links.
    passage_text = re.sub(r"\[\d{1,3}\]", "", passage_text)
    passage_text = re.sub(r"[ \t]{2,}", " ", passage_text)

    passage_text, excerpted = trim_to_excerpt(
        passage_text, excerpt_target or EXCERPT_TARGET_CHARS
    )
    if excerpted and passage_title:
        passage_title = f"{passage_title} (excerpt)"

    return {
        "source": source,
        "passage_id": str(passage_id),
        "selection_key": f"{source['id']}:{passage_id}",
        "passage_title": passage_title,
        "passage_text": passage_text,
    }


def load_source(source):
    with open(source["file"], "r", encoding="utf-8") as f:
        return json.load(f)


def balanced_companion_sources(available, day=None):
    # Each block of days contains every available companion exactly once, in
    # a deterministic shuffled order. This prevents long random droughts for
    # any voice while keeping the order from feeling like a fixed calendar.
    if not available:
        return []
    day = day or datetime.datetime.now(ZoneInfo("America/Chicago")).date()
    cycle, position = divmod(day.toordinal(), len(available))
    shuffled = sorted(available, key=lambda source: source["id"])
    random.Random(cycle).shuffle(shuffled)
    return shuffled[position:] + shuffled[:position]


def pick_companion():
    # The source follows a balanced daily rotation; its passage remains a
    # fresh random pull. If the scheduled source is empty, try the next voice
    # in today's order rather than losing the whole companion section.
    available = [s for s in COMPANION_SOURCES if s["file"].exists()]
    for source in balanced_companion_sources(available):
        passages = load_source(source)
        if not passages:
            log(f"Companion source '{source['id']}' is empty -- trying next available source.")
            continue
        passage_id = random.choice(list(passages.keys()))
        return passage_from_entry(source, passage_id, passages[passage_id])

    return None  # every available source was missing or empty


EXCERPT_TARGET_CHARS = 1100  # roughly comparable weight to a Tao chapter
ECHO_TARGET_CHARS = 520      # a counterpoint, not a second full companion
ECHO_CANDIDATE_COUNT = {"heraclitus": 8, "chuangtzu": 4, "epictetus": 5}


def trim_to_excerpt(text, target=EXCERPT_TARGET_CHARS):
    # Some source chapters (Chuang Tzu especially -- lengths vary from a
    # short parable to a multi-thousand-word essay) are far too long to
    # show whole. If a passage is long, pick a random contiguous run of
    # paragraphs from within it instead of the whole thing, so every
    # companion pull stays roughly comparable in weight to a Tao chapter.
    if len(text) <= target:
        return text, False

    paras = [p for p in text.split("\n\n") if p.strip()]
    if len(paras) <= 1:
        # No paragraph breaks to work with -- just take a leading slice.
        cut = text[:target].rsplit(" ", 1)[0]
        return cut + "...", True

    start = random.randrange(len(paras))
    chunk = [paras[start]]
    total = len(paras[start])
    i = start + 1
    while total < target and i < len(paras):
        chunk.append(paras[i])
        total += len(paras[i])
        i += 1
    excerpt = "\n\n".join(chunk)
    if len(excerpt) > target:
        excerpt = excerpt[:target].rsplit(" ", 1)[0] + "..."
    return excerpt, True


def pick_echo_candidates(companion):
    # The other two authors each offer a small candidate set. Claude chooses
    # one passage by thematic fit or productive tension, so the echo is not
    # merely another unrelated random quotation.
    remaining = [
        source for source in COMPANION_SOURCES
        if source["id"] != companion["source"]["id"] and source["file"].exists()
    ]
    candidates = []
    for source in remaining:
        passages = load_source(source)
        if not passages:
            continue
        count = min(ECHO_CANDIDATE_COUNT.get(source["id"], 4), len(passages))
        for passage_id in random.sample(list(passages.keys()), count):
            candidates.append(
                passage_from_entry(
                    source, passage_id, passages[passage_id], ECHO_TARGET_CHARS
                )
            )
    return candidates


RELATIONSHIP_FRAMING = {
    "complement": (
        "This companion text (Chuang Tzu) comes from the SAME Taoist lineage "
        "as the Tao Te Ching, sharing its commitment to non-striving -- but "
        "taught through story, parable, and dream rather than compressed "
        "aphorism. The Confluence should note how the same teaching is "
        "being carried by a different mode (story vs. aphorism), not a "
        "different claim. Be specific to what was actually pulled today, "
        "not a generic 'both are wise' statement."
    ),
    "convergence": (
        "This companion text (Heraclitus) comes from an INDEPENDENT "
        "tradition -- pre-Socratic Greek, no historical contact with "
        "Taoism whatsoever -- yet converges on strikingly similar "
        "conclusions about flux, the unity of opposites, and an underlying "
        "order to things. The Confluence should make that independence "
        "the point: these traditions never touched, and the insight showed "
        "up anyway. Be specific to what was actually pulled today, not a "
        "generic 'great minds think alike' statement."
    ),
    "counterweight": (
        "This companion text (Epictetus) brings a DISTINCT Stoic emphasis: "
        "freedom through the disciplined use of judgment, desire, and choice. "
        "Let it create useful friction with Taoist non-forcing and acceptance "
        "rather than translating it into Taoist language. Epictetus is direct "
        "and practical, sometimes stern, but he is not advocating emotional "
        "suppression, hustle culture, or indifference to other people. Preserve "
        "the boundary he draws between what happens and the character of our "
        "response. Be specific to today's actual passages."
    ),
    "opposite": (
        "This companion text comes from a tradition that reaches a similar "
        "diagnosis but an OPPOSITE prescription. Name the actual mechanism "
        "of that opposition plainly and specifically -- not a vague "
        "'different perspectives' gesture."
    ),
}


def reflect_confluence(client, tao_num, tao_verse, companion, echo_candidates):
    source = companion["source"]
    label = source["label"]
    framing = RELATIONSHIP_FRAMING.get(source["relationship"], "")
    title_line = f" ({companion['passage_title']})" if companion["passage_title"] else ""
    echo_labels = ", ".join(dict.fromkeys(
        candidate["source"]["label"] for candidate in echo_candidates
    ))
    candidates = []
    for candidate in echo_candidates:
        candidate_title = f" — {candidate['passage_title']}" if candidate["passage_title"] else ""
        candidates.append(
            f"KEY {candidate['selection_key']}{candidate_title}:\n"
            f"{candidate['passage_text']}"
        )
    candidate_text = "\n\n---\n\n".join(candidates)

    prompt = f"""You are contributing to a private morning contemplative dashboard for one person who has a long daily Tao Te Ching practice and is active in AA recovery.

Today's Tao Te Ching chapter (Chapter {tao_num}, Legge translation):
\"\"\"
{tao_verse}
\"\"\"

Today's FULL companion passage, from {label}{title_line}:
\"\"\"
{companion['passage_text']}
\"\"\"

{framing}

Choose one SHORT echo from the other available voices ({echo_labels}) below.
Choose by genuine resonance or productive tension with BOTH the Tao anchor and
the full companion. Do not force agreement. The echo author should remain a
distinct third voice, not a source of decorative quotation.

Whenever Epictetus appears, preserve his real emphasis on judgment, desire,
choice, and responsibility. Do not flatten him into emotional suppression,
internet Stoicism, hustle culture, or a generic version of the Serenity Prayer.

{candidate_text}

Return ONLY a JSON object, no preamble, no markdown fences, with exactly these keys:

{{
  "companion_interpretation": "A plain-language interpretation of what the FULL companion passage is pointing at, on its own terms. 3-4 sentences. Clear, grounded, no jargon.",
  "companion_reflection": "A reflection reading the full companion against contemporary life. Contemplative, non-partisan, no political sides or named figures. 3-4 sentences.",
  "echo_key": "The exact source:passage KEY of the one strongest echo candidate.",
  "echo_note": "Why this short echo belongs in today's conversation. Name its specific image or claim and do not merely say that all three agree. 2-3 sentences.",
  "where_meet": "Where all three texts genuinely meet, using concrete language from today's actual passages. 2-3 sentences.",
  "where_differ": "Where their voices, methods, or claims meaningfully differ. Preserve the difference instead of smoothing it away. 2-3 sentences.",
  "practice": "One quiet, specific practice or question to carry today, arising from the three-way conversation. 1-2 sentences, in second person."
}}

The Tao Te Ching is always the anchor. {label} is today's full companion;
one of the remaining voices is the brief echo. Write with warmth and depth
but economy. This is for quiet morning reflection."""

    msg = client.messages.create(
        model=MODEL,
        max_tokens=1400,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    text = text.replace("```json", "").replace("```", "").strip()
    result = json.loads(text)
    required = {
        "companion_interpretation", "companion_reflection", "echo_key",
        "echo_note", "where_meet", "where_differ", "practice",
    }
    missing = required.difference(result)
    if missing:
        raise ValueError(f"Confluence response missing keys: {', '.join(sorted(missing))}")
    return result


def reflect(client, num, verse):
    prompt = f"""You are contributing to a private morning contemplative dashboard for one person who has a long daily Tao Te Ching practice and is active in AA recovery. Today's randomly selected chapter is Chapter {num}, in James Legge's 1891 translation:

\"\"\"
{verse}
\"\"\"

Write three short movements reflecting on THIS chapter. Return ONLY a JSON object, no preamble, no markdown fences, with exactly these keys:

{{
  "interpretation": "A plain-language interpretation of what this chapter is pointing at. 3-4 sentences. Clear, grounded, no jargon. Help the reader understand the chapter's core teaching.",
  "reflection": "A reflection reading this chapter against the current state of the world as a backdrop -- contemporary American life: political division, war abroad, religious tension, the noise and grasping of modern culture. Stay contemplative and strictly non-partisan; do not take political sides or name parties/figures. Use the world's current condition as a mirror for the chapter's wisdom -- what does this 2500-year-old verse notice about how we are living now? 4-5 sentences.",
  "meditation": "A short meditation or intention to carry for the rest of the day, drawn from this chapter. 2-3 sentences, gentle and practical, in second person ('today, notice...'). Something to hold, not a lecture."
}}

Write with warmth and depth but economy. This is for quiet morning reflection."""

    msg = client.messages.create(
        model=MODEL,
        max_tokens=900,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    # Strip accidental fences
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# HTML render (parchment/brass aesthetic, matches jdb-builds.com)
# ---------------------------------------------------------------------------
def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_companion_html(companion, confluence):
    if not companion:
        return ""
    source = companion["source"]
    verse_html = "".join(f"<p>{esc(p)}</p>" for p in companion["passage_text"].split("\n\n") if p.strip())
    title_html = f'<div class="chno">{esc(companion["passage_title"])}</div>' if companion["passage_title"] else ""
    return f"""
  <div class="tao companion">
    <div class="eyebrow">{esc(source['label'])} \u00b7 {esc(source['sublabel'])}</div>
    {title_html}

    <div class="verse">{verse_html}</div>

    <div class="movement">
      <h4>What it's pointing at</h4>
      <p>{esc(confluence['companion_interpretation'])}</p>
    </div>

    <div class="movement">
      <h4>Read against today</h4>
      <p>{esc(confluence['companion_reflection'])}</p>
    </div>
  </div>
"""


def build_echo_html(echo, confluence):
    if not echo:
        return ""
    source = echo["source"]
    verse_html = "".join(
        f"<p>{esc(p)}</p>" for p in echo["passage_text"].split("\n\n") if p.strip()
    )
    title_html = f'<div class="echo-title">{esc(echo["passage_title"])}</div>' if echo["passage_title"] else ""
    return f"""
  <div class="echo">
    <div class="eyebrow">The Echo · {esc(source['label'])}</div>
    {title_html}
    <div class="verse">{verse_html}</div>
    <p class="echo-note">{esc(confluence['echo_note'])}</p>
  </div>
"""


def build_confluence_html(confluence):
    if not confluence:
        return ""
    return f"""
  <div class="confluence">
    <div class="eyebrow">The Confluence</div>
    <div class="confluence-intro">Three voices, one morning — without making them say the same thing.</div>

    <div class="movement">
      <h4>Where they meet</h4>
      <p>{esc(confluence['where_meet'])}</p>
    </div>

    <div class="movement">
      <h4>Where they part</h4>
      <p>{esc(confluence['where_differ'])}</p>
    </div>

    <div class="movement meditation">
      <h4>To carry today</h4>
      <p>{esc(confluence['practice'])}</p>
    </div>
  </div>
"""


def build_html(num, verse, refl, companion=None, echo=None, confluence=None):
    now = datetime.datetime.now(ZoneInfo("America/Chicago"))
    datestr = now.strftime("%A, %B %-d, %Y") if os.name != "nt" else now.strftime("%A, %B %d, %Y")
    verse_html = "".join(f"<p>{esc(p)}</p>" for p in verse.split("\n\n") if p.strip())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Discipline \u2014 {datestr}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..700;1,9..144,300..600&family=Inter+Tight:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  :root{{
    --paper:#100E17;--paper-2:#171421;--line-2:#332C3D;
    --ink:#F0EDE8;--ink-dim:#B8B1C3;--brass:#C4956A;--brass-bright:#E0B47F;
    --display:"Fraunces",Georgia,serif;--body:"Inter Tight",system-ui,sans-serif;
    --mono:"JetBrains Mono",ui-monospace,monospace;
  }}
  body{{background:radial-gradient(circle at 84% 8%,rgba(196,149,106,.09),transparent 30rem),radial-gradient(circle at 10% 58%,rgba(122,158,138,.07),transparent 34rem),var(--paper);color:var(--ink);font-family:var(--body);line-height:1.6;
    -webkit-font-smoothing:antialiased;padding:0 0 60px}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:760px;margin:0 auto;padding:0 28px}}
  .topnav{{display:flex;align-items:center;justify-content:space-between;
    padding:16px 0;border-bottom:1px solid var(--line-2)}}
  .topnav .home{{font-family:var(--mono);font-size:12px;letter-spacing:.18em;
    text-transform:uppercase;color:var(--ink-dim);transition:color .2s}}
  .topnav .home span{{color:var(--brass);font-weight:600}}
  .topnav .home:hover{{color:var(--brass)}}
  .topnav .here{{font-family:var(--display);font-style:italic;font-weight:300;
    font-size:14px;color:var(--ink-dim)}}
  .top{{padding:56px 0 28px;border-bottom:1px solid var(--line-2);margin-bottom:40px}}
  .top .kicker{{font-family:var(--mono);font-size:11px;letter-spacing:.28em;text-transform:uppercase;color:var(--brass);margin-bottom:14px}}
  .top h1{{font-family:var(--display);font-weight:330;font-size:clamp(34px,5vw,52px);letter-spacing:-.02em;line-height:1.04}}
  .top .date{{font-family:var(--mono);font-size:12px;letter-spacing:.1em;color:var(--ink-dim);margin-top:14px;text-transform:uppercase}}

  .section{{margin-bottom:18px}}
  .card-link{{display:block;border:1px solid var(--line-2);border-radius:8px;padding:22px 24px;transition:.2s;background:rgba(255,255,255,.03)}}
  .card-link:hover{{border-color:var(--brass);background:var(--paper-2);transform:translateY(-1px)}}
  .card-link .row{{display:flex;align-items:center;justify-content:space-between;gap:16px}}
  .card-link .label{{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--brass);margin-bottom:7px}}
  .card-link h3{{font-family:var(--display);font-weight:400;font-size:21px;letter-spacing:-.01em}}
  .card-link p{{font-size:14px;color:var(--ink-dim);margin-top:5px}}
  .card-link .go{{font-family:var(--mono);font-size:12px;color:var(--ink-dim);white-space:nowrap}}
  .card-link:hover .go{{color:var(--brass)}}

  .tao{{margin-top:34px;border-top:1px solid var(--line-2);padding-top:40px}}
  .tao.companion{{margin-top:40px}}
  .eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--brass);margin-bottom:8px}}
  .tao .chno{{font-family:var(--display);font-style:italic;font-weight:300;font-size:clamp(26px,4vw,40px);color:var(--ink);margin-bottom:24px}}
  .verse{{border-left:2px solid var(--brass);padding:4px 0 4px 26px;margin:0 0 36px}}
  .verse p{{font-family:var(--display);font-weight:300;font-size:18px;line-height:1.7;color:var(--ink);margin-bottom:1rem}}
  .verse p:last-child{{margin-bottom:0}}
  .movement{{margin-bottom:32px}}
  .movement h4{{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--brass);margin-bottom:12px}}
  .movement p{{font-size:16.5px;line-height:1.72;color:var(--ink)}}
  .movement.meditation{{background:var(--paper-2);border-radius:8px;padding:24px 26px}}
  .movement.meditation p{{font-family:var(--display);font-style:italic;font-weight:300;font-size:18px;color:var(--ink)}}

  .echo{{margin-top:40px;padding:28px 30px;border:1px solid var(--line-2);border-radius:8px;background:linear-gradient(135deg,rgba(196,149,106,.07),rgba(255,255,255,.02))}}
  .echo-title{{font-family:var(--display);font-style:italic;font-weight:300;font-size:21px;margin:0 0 18px}}
  .echo .verse{{margin-bottom:20px;padding-left:22px}}
  .echo .verse p{{font-size:20px;line-height:1.6}}
  .echo-note{{font-size:15.5px;line-height:1.7;color:var(--ink-dim)}}

  .confluence{{margin-top:40px;border-top:1px solid var(--brass);padding-top:40px}}
  .confluence-intro{{font-family:var(--display);font-style:italic;font-weight:300;font-size:clamp(24px,4vw,34px);line-height:1.25;margin:6px 0 32px;color:var(--ink)}}
  .confluence .movement:not(.meditation){{padding-left:18px;border-left:1px solid var(--line-2)}}

  footer{{margin-top:48px;padding-top:28px;border-top:1px solid var(--line-2);
    font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--ink-dim);text-align:center;line-height:1.8}}
</style>
</head>
<body>
<div class="wrap">

  <div class="topnav">
    <a class="home" href="https://jdb-builds.com"><span>JDB</span> · Home</a>
    <span class="here">Daily Discipline</span>
  </div>

  <div class="top">
    <div class="kicker">Daily Discipline</div>
    <h1>Every 24 Hours,<br>Begin Again.</h1>
    <div class="date">{datestr}</div>
  </div>

  <div class="section">
    <a class="card-link" href="{LINKS['aa_reflection']}" target="_blank" rel="noopener">
      <div class="row">
        <div>
          <div class="label">Alcoholics Anonymous</div>
          <h3>Daily Reflection</h3>
          <p>Today's reflection from the fellowship.</p>
        </div>
        <div class="go">Open \u2197</div>
      </div>
    </a>
  </div>

  <div class="section">
    <a class="card-link" href="{LINKS['hazelden']}" target="_blank" rel="noopener">
      <div class="row">
        <div>
          <div class="label">Hazelden Betty Ford</div>
          <h3>Twenty-Four Hours a Day</h3>
          <p>Thought, meditation, and prayer for the day.</p>
        </div>
        <div class="go">Open \u2197</div>
      </div>
    </a>
  </div>

  <div class="section">
    <a class="card-link" href="{LINKS['grapevine']}" target="_blank" rel="noopener">
      <div class="row">
        <div>
          <div class="label">AA Grapevine</div>
          <h3>Quote of the Day</h3>
          <p>A line from the meeting in print.</p>
        </div>
        <div class="go">Open \u2197</div>
      </div>
    </a>
  </div>

  <div class="tao">
    <div class="eyebrow">Tao Te Ching \u00b7 Legge translation</div>
    <div class="chno">Chapter {num}</div>

    <div class="verse">{verse_html}</div>

    <div class="movement">
      <h4>What it's pointing at</h4>
      <p>{esc(refl['interpretation'])}</p>
    </div>

    <div class="movement">
      <h4>Read against today</h4>
      <p>{esc(refl['reflection'])}</p>
    </div>

    <div class="movement meditation">
      <h4>To carry today</h4>
      <p>{esc(refl['meditation'])}</p>
    </div>
  </div>
{build_companion_html(companion, confluence)}
{build_echo_html(echo, confluence)}
{build_confluence_html(confluence)}
  <footer>
    Daily Discipline \u00b7 jdb-builds.com<br>
    Tao Te Ching, James Legge translation (1891, public domain) \u00b7 Fresh reflection generated each morning<br>
    Companion library: public-domain Chuang Tzu and Heraclitus texts \u00b7 Epictetus, George Long translation<br>
    The Tao remains the daily anchor \u00b7 One full companion rotates among Chuang Tzu, Heraclitus, and Epictetus<br>
    The other voices offer thematically chosen echoes \u00b7 The Confluence names where three meet, where they part, and what to carry<br>
    Daily Reflection, Twenty-Four Hours, and Grapevine link to their sources \u2014 please support them
  </footer>

</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    gate()
    log("\u2500\u2500 Daily Discipline Generator \u2500\u2500")
    if not API_KEY:
        log("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)
    if not TAO_FILE.exists():
        log(f"ERROR: {TAO_FILE.name} not found. Run build_tao_data.py first.")
        sys.exit(1)

    tao = load_tao()
    num, verse = pick_chapter(tao)
    log(f"Today's chapter: {num}")

    client = anthropic.Anthropic(api_key=API_KEY)
    log("Generating reflection with Claude...")
    try:
        refl = reflect(client, num, verse)
    except Exception as e:
        log(f"Reflection generation failed: {e}")
        sys.exit(1)

    companion = pick_companion()
    echo = None
    confluence = None
    if companion:
        log(f"Companion pick: {companion['source']['label']} \u2014 {companion['passage_id']}")
        echo_candidates = pick_echo_candidates(companion)
        if not echo_candidates:
            log("No echo candidates found -- skipping the companion dialogue.")
            companion = None
        else:
            echo_sources = ", ".join(dict.fromkeys(
                candidate["source"]["label"] for candidate in echo_candidates
            ))
            log(
                f"Selecting an echo from {echo_sources} "
                f"({len(echo_candidates)} candidates)..."
            )
        try:
            if companion:
                confluence = reflect_confluence(
                    client, num, verse, companion, echo_candidates
                )
                echo_key = str(confluence["echo_key"])
                echo = next(
                    candidate for candidate in echo_candidates
                    if candidate["selection_key"] == echo_key
                )
                log(
                    f"Echo selected: {echo['source']['label']} \u2014 "
                    f"{echo['passage_id']}"
                )
        except Exception as e:
            log(f"Confluence generation failed (continuing with Tao only): {e}")
            companion = None
            echo = None
            confluence = None
    else:
        log("No companion source files found yet -- skipping companion section.")

    html = build_html(num, verse, refl, companion, echo, confluence)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"Built dashboard -> {OUTPUT_FILE}")

    # In GitHub Actions, the workflow handles the push.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        log("Running in GitHub Actions; workflow handles push.")
    else:
        log("Local run complete. Commit and push when ready.")
    log("Done.")


if __name__ == "__main__":
    main()
