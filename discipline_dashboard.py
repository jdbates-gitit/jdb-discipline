#!/usr/bin/env python3
# discipline_dashboard.py
# Daily Discipline — a morning contemplative dashboard.
#
# Four sections:
#   1. Daily Reflection (AA)      -> launchpad card linking to aa.org
#   2. Twenty-Four Hours a Day    -> launchpad card linking to Hazelden
#   3. Grapevine Quote of the Day -> launchpad card linking to AA Grapevine
#   4. Tao Te Ching exploration   -> random chapter (local Legge text) +
#        Claude-generated: plain-language interpretation, reflection against
#        today's world, and a short meditation to carry.
#
# Reads Legge text ONLY from local tao_te_ching_legge.json (no outside source).
# Windowed run gate (2-5 AM CT) handles GitHub Actions cron lag.

import os
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
# Windowed run gate (2-5 AM CT). Mirrors the proven jdb-dashboard pattern.
# ---------------------------------------------------------------------------
def gate():
    if os.environ.get("RUN_NOW") == "1":
        return
    now = datetime.datetime.now(ZoneInfo("America/Chicago"))
    today = now.strftime("%Y-%m-%d")
    hour = now.hour
    if not (2 <= hour < 6):  # window 2:00-5:59 AM CT (generous tail past 5)
        log(f"Outside run window (CT hour={hour}). Exiting cleanly.")
        sys.exit(0)
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


def build_html(num, verse, refl):
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
    --paper:#F2EDE1;--paper-2:#EAE3D3;--line-2:#C9BFA6;
    --ink:#1E1B14;--ink-dim:#6B6453;--brass:#9A6B16;--brass-bright:#B5841F;
    --display:"Fraunces",Georgia,serif;--body:"Inter Tight",system-ui,sans-serif;
    --mono:"JetBrains Mono",ui-monospace,monospace;
  }}
  body{{background:var(--paper);color:var(--ink);font-family:var(--body);line-height:1.6;
    -webkit-font-smoothing:antialiased;padding:0 0 60px}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:760px;margin:0 auto;padding:0 28px}}
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
  .tao .eyebrow{{font-family:var(--mono);font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:var(--brass);margin-bottom:8px}}
  .tao .chno{{font-family:var(--display);font-style:italic;font-weight:300;font-size:clamp(26px,4vw,40px);color:var(--ink);margin-bottom:24px}}
  .verse{{border-left:2px solid var(--brass);padding:4px 0 4px 26px;margin:0 0 36px}}
  .verse p{{font-family:var(--display);font-weight:300;font-size:18px;line-height:1.7;color:var(--ink);margin-bottom:1rem}}
  .verse p:last-child{{margin-bottom:0}}
  .movement{{margin-bottom:32px}}
  .movement h4{{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--brass);margin-bottom:12px}}
  .movement p{{font-size:16.5px;line-height:1.72;color:var(--ink)}}
  .movement.meditation{{background:var(--paper-2);border-radius:8px;padding:24px 26px}}
  .movement.meditation p{{font-family:var(--display);font-style:italic;font-weight:300;font-size:18px;color:var(--ink)}}

  footer{{margin-top:48px;padding-top:28px;border-top:1px solid var(--line-2);
    font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--ink-dim);text-align:center;line-height:1.8}}
</style>
</head>
<body>
<div class="wrap">

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

  <footer>
    Daily Discipline \u00b7 jdb-builds.com<br>
    Tao Te Ching, James Legge translation (1891, public domain) \u00b7 Reflection generated fresh each morning<br>
    Reflection, Twenty-Four Hours, and Grapevine link to their sources \u2014 please support them
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

    html = build_html(num, verse, refl)
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
