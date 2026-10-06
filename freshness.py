"""The public page, not a green job or a date flag, is the freshness contract."""

import datetime
import html
import json
import re

VERSION = 1
ROLES = ("lead", "companion", "echo")


def manifest_script(readings, day, mode):
    manifest = {
        "version": VERSION,
        "date": day.isoformat(),
        "editorial_mode": mode,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "selections": {role: reading["selection_key"] for role, reading in zip(ROLES, readings)},
    }
    encoded = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script id="discipline-freshness" type="application/json">{encoded}</script>'


def text_present(markup):
    return bool(html.unescape(re.sub(r"<[^>]*>", "", markup)).strip())


def validate_page(page, day):
    """Raise on stale, incomplete, or mismatched output; return its manifest."""
    matches = re.findall(r'<script id="discipline-freshness" type="application/json">(.*?)</script>', page, re.S)
    if len(matches) != 1:
        raise ValueError("Missing or duplicate freshness manifest")
    manifest = json.loads(matches[0])
    expected = day.isoformat()
    if not isinstance(manifest, dict):
        raise ValueError("Malformed freshness manifest")
    if type(manifest.get("version")) is not int or manifest.get("version") != VERSION or manifest.get("date") != expected:
        raise ValueError("Wrong contract version or reading date")
    if manifest.get("editorial_mode") not in ("ai", "fixed"):
        raise ValueError("Unknown editorial mode")
    selections = manifest.get("selections", {})
    if not isinstance(selections, dict) or set(selections) != set(ROLES):
        raise ValueError("Three distinct reading selections are required")
    for role in ROLES:
        key = selections[role]
        if not isinstance(key, str) or not re.fullmatch(r"[a-z_]+:[A-Za-z0-9_]+", key):
            raise ValueError("Invalid selection key")
        blocks = re.findall(rf'<section\b[^>]*data-reading-role="{role}"[^>]*>(.*?)</section>', page, re.S)
        if len(blocks) != 1:
            raise ValueError(f"Missing or duplicate {role} reading")
        section = re.search(rf'<section\b[^>]*data-reading-role="{role}"[^>]*>', page).group(0)
        if f'data-selection-key="{html.escape(key, quote=True)}"' not in section:
            raise ValueError("Reading does not match manifest")
        verse = re.search(r'<div class="verse">(.*?)</div>', blocks[0], re.S)
        if not verse or not text_present(verse[1]):
            raise ValueError(f"Empty {role} source text")
        note_pattern = r'<p class="echo-note">(.*?)</p>' if role == "echo" else r'<div class="movement">.*?<p>(.*?)</p>'
        note = re.search(note_pattern, blocks[0], re.S)
        if not note or not text_present(note[1]):
            raise ValueError(f"Missing {role} reading note")
    if len(set(selections.values())) != 3:
        raise ValueError("Three distinct reading selections are required")
    if manifest["editorial_mode"] == "fixed" and 'id="editorial-status"' not in page:
        raise ValueError("Fixed prompts must be visibly labelled")
    for pattern in (
        r'<h2 id="daily-question">(.*?)</h2>',
        r'<section class="confluence"[^>]*>.*?<p>(.*?)</p>',
        r'<section class="carry"[^>]*>(.*?)</section>',
        r'<details class="return">(.*?)</details>',
        r'<details class="trail">(.*?)</details>',
    ):
        block = re.search(pattern, page, re.S)
        if not block or not text_present(block[1]):
            raise ValueError("Incomplete question, Confluence, or practice structure")
    carry = re.search(r'<section class="carry"[^>]*>(.*?)</section>', page, re.S)[1]
    for label in ("Notice", "Surrender", "Act"):
        step = re.search(rf'<dt>{label}</dt><dd>(.*?)</dd>', carry, re.S)
        if not step or not text_present(step[1]):
            raise ValueError(f"Missing {label} practice")
    evening = re.search(r'<details class="return">(.*?)</details>', page, re.S)[1]
    question = re.search(r'<p class="night-question">(.*?)</p>', evening, re.S)
    if not question or not text_present(question[1]) or f'data-note-date="{expected}"' not in evening:
        raise ValueError("Missing today's evening question")
    if f'data-discipline-date="{expected}"' not in page or "</body></html>" not in page:
        raise ValueError("Missing page date or incomplete document")
    trail = re.search(r'<details class="trail">(.*?)</details>\s*<footer>', page, re.S)
    if not trail or '<ul class="trail-list">' not in trail[1] or f'datetime="{expected}"' not in trail[1]:
        raise ValueError("Missing today's Seven-Day Trail entry")
    return manifest
