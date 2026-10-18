"""Archive approved Dhammapada and Whitman editions; never runs in the daily job.

Only source formatting and note markers are removed, never translated wording.
The generated JSON is checked into the local library after review.
"""
import concurrent.futures
import hashlib
import html
import json
import re
import textwrap
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
DHAMMA_ROOT = "https://accesstoinsight.org/tipitaka/kn/dhp/"
WHITMAN_URL = "https://www.gutenberg.org/files/1322/1322-h/1322-h.htm"
DHAMMA_LICENSE = (
    "©1985 Buddhist Publication Society. You may copy, reformat, reprint, republish, "
    "and redistribute this work in any medium whatsoever, provided that: "
    "(1) you only make such copies, etc. available free of charge and, in the case "
    "of reprinting, only in quantities of no more than 50 copies; "
    "(2) you clearly indicate that any derivatives of this work (including "
    "translations) are derived from this source document; and "
    "(3) you include the full text of this license in any copies or derivatives "
    "of this work. Otherwise, all rights reserved."
)
DHAMMA_CHAPTERS = (
    "Pairs", "Heedfulness", "The Mind", "Flowers", "The Fool", "The Wise Man",
    "The Arahant or Perfected One", "The Thousands", "Evil", "Violence",
    "Old Age", "The Self", "The World", "The Buddha", "Happiness", "Affection",
    "Anger", "Impurity", "The Just", "The Path", "Miscellaneous",
    "The State of Woe", "The Elephant", "Craving", "The Monk", "The Holy Man",
)
# Coherent numbered sections, not a collection of unattributed one-line quotes.
# Open Road 10 is omitted: its exclusionary health/alcohol language is a poor fit
# for this recovery morning practice. No words inside included sections change.
WHITMAN_SELECTIONS = {
    "Song of the Open Road": ("open_road", tuple(n for n in range(1, 16) if n != 10)),
    "Song of Myself": ("myself", (1, 2, 6, 7, 14, 17, 20, 21, 30, 31, 32, 44, 46, 48, 49, 50, 51, 52)),
    "Crossing Brooklyn Ferry": ("ferry", tuple(range(1, 10))),
    "A Song of the Rolling Earth": ("rolling_earth", (1, 2, 3, 4)),
    "Miracles": ("miracles", None),
    "O Me! O Life!": ("o_me_o_life", None),
    "When I Heard the Learn’d Astronomer": ("astronomer", None),
    "On the Beach at Night Alone": ("beach_night", None),
    "A Noiseless Patient Spider": ("spider", None),
    "A Clear Midnight": ("clear_midnight", None),
    "The Untold Want": ("untold_want", None),
    "This Moment Yearning and Thoughtful": ("yearning", None),
}


def plain(markup):
    markup = re.sub(r'<a\b[^>]*href=["\'][^"\']*(?:#note|#fn)[^"\']*["\'][^>]*>.*?</a>', '', markup, flags=re.S | re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", markup))).strip()


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Daily Discipline source archive (local build)"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8-sig")


def parse_dhamma_chapter(markup, chapter, title):
    verses = []
    for paragraph in re.findall(r'<p\b[^>]*>(.*?)</p>', markup, re.S | re.I):
        anchor = re.search(r'id=["\'](?:dhp|verse)-(\d+)(?:-\d+)?["\']', paragraph)
        heading = re.search(r'<b>([\d\-–]+)\.?\s*</b>', paragraph)
        if not anchor or not heading:
            continue
        label = heading[1].replace("-", "–")
        numbers = [int(n) for n in re.findall(r"\d+", label)]
        if not numbers or numbers[0] != int(anchor[1]):
            raise ValueError(f"Unrecognized Dhammapada verse heading: {label}")
        numbers = list(range(numbers[0], numbers[-1] + 1))
        verse = re.sub(r'^[\d\-–]+\.?\s*', '', plain(paragraph))
        verse = re.sub(r"\s*\[\d+\]", "", verse).strip()
        if not verse:
            raise ValueError(f"Empty Dhammapada verse {label}")
        verses.append({"label": label, "numbers": numbers, "text": verse})
    if not verses:
        raise ValueError(f"No verses in chapter {chapter}")
    readings = {}
    for start in range(0, len(verses), 3):
        units = verses[start:start + 3]
        first, last = units[0]["numbers"][0], units[-1]["numbers"][-1]
        verse_range = str(first) if first == last else f"{first}–{last}"
        readings[f"v{first}_{last}"] = {
            "title": f"{title} · verses {verse_range}", "chapter": chapter,
            "source_url": f"{DHAMMA_ROOT}dhp.{chapter:02d}.budd.html#dhp-{first}",
            "units": units, "text": "\n\n".join(unit["text"] for unit in units),
        }
    return readings


def parse_whitman(markup):
    last_title, readings, found, poems = "", {}, set(), {}
    tokens = re.finditer(r"<(p|h2)\b[^>]*>(.*?)</\1>|<pre\b[^>]*>(.*?)</pre>", markup, re.S | re.I)
    for token in tokens:
        if token[1]:
            last_title = plain(token[2])
            continue
        if last_title not in WHITMAN_SELECTIONS:
            continue
        poems.setdefault(last_title, []).append(token[3])
    for title, blocks in poems.items():
        prefix, wanted = WHITMAN_SELECTIONS[title]
        body = html.unescape(re.sub(r"<[^>]+>", "", "\n\n".join(blocks))).replace("\r\n", "\n")
        headings = list(re.finditer(r"(?m)^[ \t]*(\d{1,2})[ \t]*$", body)) if wanted else []
        sections = []
        if wanted:
            for index, heading in enumerate(headings):
                number = int(heading[1])
                if number in wanted:
                    end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
                    sections.append((f"{prefix}_{number}", f"{title} · section {number}", body[heading.end():end]))
            if len(sections) != len(wanted):
                raise ValueError(f"Missing numbered section in {title}: found {[int(h[1]) for h in headings]}")
        else:
            sections = [(prefix, title, body)]
        for key, section_title, raw in sections:
            text = textwrap.dedent(raw).strip()
            stanzas = [stanza.strip("\n") for stanza in re.split(r"\n[ \t]*\n", text) if stanza.strip()]
            readings[key] = {
                "title": section_title, "poem": title, "source_url": WHITMAN_URL,
                "units": [{"label": str(index + 1), "text": stanza} for index, stanza in enumerate(stanzas)],
                "text": "\n\n".join(stanzas),
            }
        found.add(title)
    if found != set(WHITMAN_SELECTIONS):
        raise ValueError(f"Missing Whitman poems: {set(WHITMAN_SELECTIONS) - found}")
    return readings


def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        chapters = list(executor.map(fetch, [f"{DHAMMA_ROOT}dhp.{n:02d}.budd.html" for n in range(1, 27)]))
    dhamma = {}
    for chapter, (title, markup) in enumerate(zip(DHAMMA_CHAPTERS, chapters), 1):
        dhamma.update(parse_dhamma_chapter(markup, chapter, title))
    verse_numbers = [n for entry in dhamma.values() for unit in entry["units"] for n in unit["numbers"]]
    if verse_numbers != list(range(1, 424)):
        raise ValueError("Dhammapada must preserve every verse, 1–423, exactly once")
    whitman_markup = fetch(WHITMAN_URL)
    whitman = parse_whitman(whitman_markup)
    SOURCES.mkdir(exist_ok=True)
    metadata = {
        "dhammapada": {"translator": "Acharya Buddharakkhita", "edition": "Buddhist Publication Society, 1985; Access to Insight transcription",
            "source_url": DHAMMA_ROOT + "dhp.intro.budd.html", "rights": "Copyrighted; conditional free redistribution, not public domain",
            "license": DHAMMA_LICENSE, "chapters_sha256": [hashlib.sha256(text.encode()).hexdigest() for text in chapters],
            "reading_count": len(dhamma), "verse_count": len(verse_numbers)},
        "whitman": {"author": "Walt Whitman", "edition": "Leaves of Grass, Project Gutenberg eBook 1322",
            "source_url": WHITMAN_URL, "rights": "Public domain in the USA", "sha256": hashlib.sha256(whitman_markup.encode()).hexdigest(),
            "reading_count": len(whitman), "poems": list(WHITMAN_SELECTIONS),
            "curation": "Selected complete poems and numbered sections. Song of the Open Road section 10 omitted for its exclusionary health/alcohol language. Text within included selections is not rewritten."},
    }
    for name, readings in (("dhammapada", dhamma), ("whitman", whitman)):
        # The conditional license accompanies even a standalone JSON download.
        payload = {"_metadata": metadata[name], "readings": readings}
        (SOURCES / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (SOURCES / "reading_provenance.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Archived {len(dhamma)} Dhammapada readings (423 verses) and {len(whitman)} Whitman readings. No AI calls or publication.")


if __name__ == "__main__":
    main()
