#!/usr/bin/env python3
"""Build all 150 Psalms from Project Gutenberg's public-domain KJV (eBook 10)."""

import json
import re
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_URL = "https://www.gutenberg.org/cache/epub/10/pg10.txt"
OUTPUT_FILE = HERE / "sources" / "psalms.json"


def parse_psalms(source_text):
    text = source_text.replace("\r\n", "\n").replace("\r", "\n")
    # The heading also appears in the table of contents. Only the book body
    # has numbered verses immediately after its heading.
    heading = re.search(r"^The Book of Psalms\s+1:1\s", text, re.MULTILINE)
    if not heading:
        raise ValueError("Could not find the Psalms book body.")
    end = re.search(r"^The Proverbs\s*$", text[heading.end():], re.MULTILINE)
    if not end:
        raise ValueError("Could not find the end of Psalms.")
    book = text[heading.start():heading.end() + end.start()]
    matches = list(re.finditer(r"(?<!\S)(\d{1,3}):(\d{1,3})\s+", book))
    psalms = {}
    for index, match in enumerate(matches):
        chapter, verse = map(int, match.groups())
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(book)
        words = re.sub(r"\s+", " ", book[match.end():content_end]).strip()
        entry = psalms.setdefault(str(chapter), {"title": f"Psalm {chapter}", "verses": []})
        if not words or verse != len(entry["verses"]) + 1:
            raise ValueError(f"Missing or out-of-order verse at Psalm {chapter}:{verse}.")
        entry["verses"].append({"number": verse, "text": words})
    if set(psalms) != {str(number) for number in range(1, 151)}:
        raise ValueError("Expected all 150 Psalms.")
    for entry in psalms.values():
        entry["text"] = "\n\n".join(verse["text"] for verse in entry["verses"])
    return psalms


def main():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Daily Discipline source builder"})
    with urllib.request.urlopen(request, timeout=30) as response:
        psalms = parse_psalms(response.read().decode("utf-8-sig"))
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(psalms, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(psalms)} Psalms ({sum(len(p['verses']) for p in psalms.values())} verses) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
