#!/usr/bin/env python3
# build_tao_data.py  (v3 - handles chapters that open without a "1." paragraph)
#
# Legge's Gutenberg format (#216):
#   Most chapters open "N. 1. <text>"  (chapter N, paragraph 1)
#   Some short/poem chapters open just "N." then the poem (e.g. chapter 6)
#   Inner paragraphs are numbered "1." "2." "3." ...
#
# Strategy: a chapter heading is a line beginning with "<N>." where N is the
# NEXT expected chapter number (1..81). After matching, we keep the remainder
# of that line (which may be paragraph "1." text or the start of a poem).
# Inner paragraph numbers are stripped for clean display.
#
# Run:  python build_tao_data.py
# Fallback: python build_tao_data.py --local pg216.txt

import json
import re
import sys
import urllib.request

URLS = [
    "https://www.gutenberg.org/cache/epub/216/pg216.txt",
    "https://www.gutenberg.org/files/216/216-0.txt",
]
OUT = "tao_te_ching_legge.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (tao-builder)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def get_text():
    if len(sys.argv) >= 3 and sys.argv[1] == "--local":
        with open(sys.argv[2], "r", encoding="utf-8", errors="replace") as f:
            print(f"Using local file: {sys.argv[2]}")
            return f.read()
    for url in URLS:
        try:
            print(f"Fetching: {url}")
            t = fetch(url)
            if t and len(t) > 5000:
                print(f"  OK ({len(t)} chars)")
                return t
        except Exception as e:
            print(f"  failed: {e}")
    print("\nERROR: could not fetch. Download https://www.gutenberg.org/ebooks/216 "
          "to pg216.txt and run:  python build_tao_data.py --local pg216.txt")
    sys.exit(1)


def main():
    text = get_text().replace("\r\n", "\n").replace("\r", "\n")

    s = re.search(r"\*\*\* START OF.*?\*\*\*", text, re.DOTALL)
    if s:
        text = text[s.end():]
    e = re.search(r"\*\*\* END OF.*?\*\*\*", text, re.DOTALL)
    if e:
        text = text[:e.start()]

    # Normalize "Ch. 1." opener to "1."
    text = re.sub(r"\bCh\.\s*1\.", "1.", text, count=1)

    lines = text.split("\n")

    # A candidate chapter heading: line starts with "<N>." possibly followed by
    # more text (paragraph "1." text or a poem). We confirm by checking N is the
    # next expected chapter number, which prevents inner paragraph numbers
    # (which restart at 1 each chapter) from being mistaken for chapter heads.
    head = re.compile(r"^(\d{1,2})\.(\s+|$)(.*)$")

    chapters = {}
    cur = None
    buf = []

    def flush():
        if cur is not None:
            body = "\n".join(buf)
            # strip inner paragraph numbers at line starts: "1. ", "2. ", etc.
            body = re.sub(r"(?m)^\s*\d{1,2}\.\s+", "", body)
            # also handle a lone leading number left from the heading line
            paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", body)]
            paras = [p for p in paras if p]
            chapters[str(cur)] = "\n\n".join(paras)

    for line in lines:
        stripped = line.strip()
        m = head.match(stripped)
        if m:
            n = int(m.group(1))
            expected = (cur + 1) if cur is not None else 1
            if n == expected and 1 <= n <= 81:
                flush()
                cur = n
                remainder = m.group(3).strip()
                # If remainder begins with "1." it's paragraph 1; strip that marker.
                remainder = re.sub(r"^1\.\s+", "", remainder)
                buf = [remainder] if remainder else []
                continue
        if cur is not None:
            buf.append(line)
    flush()

    found = sorted(int(k) for k in chapters)
    print(f"\nParsed {len(chapters)} chapters.")
    missing = [n for n in range(1, 82) if n not in found]
    if missing:
        print(f"WARNING: missing chapters: {missing}")
    else:
        print("All 81 chapters present.")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT}")

    for check in ("1", "6", "42", "81"):
        if check in chapters:
            print(f"\n--- Chapter {check} ---")
            print(chapters[check][:240], "...")


if __name__ == "__main__":
    main()
