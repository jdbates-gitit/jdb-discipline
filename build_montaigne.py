"""Archive bounded, complete Cotton/Hazlitt paragraphs for local review.

This manual library builder never runs in the daily workflow. No AI rewriting.
The inventory mode prints candidate paragraphs for human curation before export.
"""
import argparse
import hashlib
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = "https://www.gutenberg.org/files/3600/3600-h/3600-h.htm"
HERE = Path(__file__).resolve().parent
ESSAYS = {
    (1, "OF SOLITUDE"), (1, "OF FRIENDSHIP"), (1, "OF THE UNCERTAINTY OF OUR JUDGMENT"),
    (2, "OF BOOKS"), (2, "THAT OUR MIND HINDERS ITSELF"),
    (3, "OF REPENTANCE"), (3, "OF THE ART OF CONFERENCE"),
    (3, "OF MANAGING THE WILL"), (3, "OF EXPERIENCE"),
}


class EssayParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.book, self.chapter, self.heading, self.anchor = 0, "", "", ""
        self.capture, self.parts, self.paragraph, self.entries = None, [], 0, {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h2" or (tag == "p" and (self.book, self.chapter) in ESSAYS):
            self.capture, self.parts = tag, []
        if tag == "a" and attrs.get("id"):
            self.anchor = attrs["id"]

    def handle_data(self, text):
        if self.capture:
            self.parts.append(text)

    def handle_endtag(self, tag):
        if tag != self.capture:
            return
        text = re.sub(r"\s+", " ", "".join(self.parts)).strip()
        if tag == "h2":
            if "BOOK THE FIRST" in text:
                self.book = 1
            elif "BOOK THE SECOND" in text:
                self.book = 2
            elif "BOOK THE THIRD" in text:
                self.book = 3
            self.chapter = re.sub(r"^CHAPTER\s+[IVXLCDM]+[\s—–-]*", "", text).strip()
            self.heading, self.paragraph = self.anchor, 0
        elif text:
            self.paragraph += 1
            key = f"b{self.book}_{self.chapter.lower().replace(' ', '_')}_p{self.paragraph}"
            self.entries[key] = {
                "title": f"{self.chapter.title()} · Book {self.book} · paragraph {self.paragraph}",
                "book": self.book, "essay": self.chapter, "paragraph": self.paragraph,
                "source_url": URL + ("#" + self.heading if self.heading else ""),
                "units": [{"label": str(self.paragraph), "text": text}], "text": text,
            }
        self.capture, self.parts = None, []


def parse(markup):
    parser = EssayParser()
    parser.feed(markup)
    return parser.entries


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--inventory", action="store_true")
    args = cli.parse_args()
    with urllib.request.urlopen(URL, timeout=45) as response:
        raw = response.read()
    entries = parse(raw.decode("utf-8-sig"))
    if args.inventory:
        for key, entry in entries.items():
            text = entry["text"]
            if 180 <= len(text) <= 1250 and not text.startswith(("[", "—[")):
                print(key + "\t" + text)
        return
    chosen = json.loads((HERE / "sources" / "montaigne_curation.json").read_text(encoding="utf-8"))
    readings = {}
    for key, themes in chosen.items():
        entry = entries[key]
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z‘“])', entry["text"])
        if " ".join(sentences) != entry["text"]:
            raise ValueError("Sentence formatting changed source wording")
        readings[key] = {**entry, "themes": themes,
            "units": [{"label": str(n + 1), "text": text} for n, text in enumerate(sentences)]}
    metadata = {
        "author": "Michel de Montaigne", "translator": "Charles Cotton",
        "editor": "William Carew Hazlitt", "edition": "Essays, 1877; Project Gutenberg eBook 3600",
        "source_url": URL, "rights": "Public domain in the USA",
        "sha256": hashlib.sha256(raw).hexdigest(), "reading_count": len(readings),
        "curation": "Selected prose paragraphs, excerpted only in consecutive complete sentence groups. Spacing normalized; source wording and embedded editorial notes retained. Titles, paragraph/sentence numbers and theme tags are editorial metadata, not Montaigne's words.",
    }
    payload = {"_metadata": metadata, "readings": readings}
    (HERE / "sources" / "montaigne.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Archived {len(readings)} complete Montaigne paragraphs. No AI call or publication.")


if __name__ == "__main__":
    main()
