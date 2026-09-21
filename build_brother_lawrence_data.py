#!/usr/bin/env python3
"""Build the local Brother Lawrence source file from Project Gutenberg eBook 13871."""

import json
import re
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_URL = "https://www.gutenberg.org/cache/epub/13871/pg13871.txt"
OUTPUT_FILE = HERE / "sources" / "brother_lawrence.json"

ORDINALS = {
    "FIRST": 1,
    "SECOND": 2,
    "THIRD": 3,
    "FOURTH": 4,
    "FIFTH": 5,
    "SIXTH": 6,
    "SEVENTH": 7,
    "EIGHTH": 8,
    "NINTH": 9,
    "TENTH": 10,
    "ELEVENTH": 11,
    "TWELFTH": 12,
    "THIRTEENTH": 13,
    "FOURTEENTH": 14,
    "FIFTEENTH": 15,
}

SECTION_RE = re.compile(
    r"^(FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|"
    r"TENTH|ELEVENTH|TWELFTH|THIRTEENTH|FOURTEENTH|FIFTEENTH) "
    r"(CONVERSATION|LETTER)\.\s*$",
    re.MULTILINE,
)


def clean_section(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\[(\d+)\]", "", text)
    text = text.replace("_", "")
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", text):
        cleaned = re.sub(r"\s+", " ", paragraph).strip()
        if cleaned:
            paragraphs.append(cleaned)
    return "\n\n".join(paragraphs)


def parse_sections(source_text):
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
    start = source_text.find(start_marker)
    end = source_text.find(end_marker, start + 1)
    if start == -1 or end == -1:
        raise ValueError("Could not find the Project Gutenberg book markers.")

    book = source_text[start:end]
    matches = list(SECTION_RE.finditer(book))
    sections = {}
    for index, match in enumerate(matches):
        ordinal, kind = match.groups()
        number = ORDINALS[ordinal]
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(book)
        text = clean_section(book[content_start:content_end])
        key = f"{kind.lower()}_{number}"
        title = f"{ordinal.title()} {kind.title()}"
        sections[key] = {"title": title, "text": text}

    if len(sections) != 19:
        raise ValueError(f"Expected 19 conversations and letters; found {len(sections)}.")
    return sections


def main():
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "Daily Discipline source builder"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        source_text = response.read().decode("utf-8-sig")

    sections = parse_sections(source_text)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(sections, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(sections)} Brother Lawrence readings to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
