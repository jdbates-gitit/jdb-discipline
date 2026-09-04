#!/usr/bin/env python3
"""Build the local Epictetus source file from Project Gutenberg eBook 10661."""

import json
import re
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE_URL = "https://www.gutenberg.org/cache/epub/10661/pg10661.txt"
OUTPUT_FILE = HERE / "sources" / "epictetus.json"


def clean_section(raw):
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", raw.strip()):
        text = re.sub(r"\s*\(\[Greek:.*?\]\)", "", paragraph, flags=re.DOTALL)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def parse_encheiridion(source_text):
    source_text = source_text.replace("\r\n", "\n").replace("\r", "\n")
    start_marker = "\nTHE ENCHEIRIDION, OR MANUAL.\n"
    start = source_text.rfind(start_marker)
    if start == -1:
        raise ValueError("Could not find the Encheiridion start marker.")

    end = source_text.find("*** END OF THE PROJECT GUTENBERG EBOOK", start)
    if end == -1:
        raise ValueError("Could not find the Project Gutenberg end marker.")

    manual = source_text[start + len(start_marker):end]
    headings = list(re.finditer(r"(?m)^([IVXLCDM]+)\.\s*$", manual))
    if len(headings) != 52:
        raise ValueError(f"Expected 52 Encheiridion sections; found {len(headings)}.")

    sections = {}
    for index, heading in enumerate(headings):
        section_id = heading.group(1)
        section_end = headings[index + 1].start() if index + 1 < len(headings) else len(manual)
        text = clean_section(manual[heading.end():section_end])
        if not text:
            raise ValueError(f"Encheiridion section {section_id} is empty.")
        sections[section_id] = {
            "title": f"Encheiridion {section_id}",
            "text": text,
        }
    return sections


def main():
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "Daily Discipline source builder"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        source_text = response.read().decode("utf-8-sig")

    sections = parse_encheiridion(source_text)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as output:
        json.dump(sections, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Built {len(sections)} Epictetus sections -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
