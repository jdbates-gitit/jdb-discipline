"""Render a local fixed-prompt example without an AI call or production writes."""
import argparse
import datetime
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discipline_dashboard as discipline
from freshness import validate_page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.suffix != ".html" or output == discipline.OUTPUT_FILE or output.exists():
        parser.error("Choose a new .html preview file, not production index.html")
    day = datetime.datetime.now(discipline.TIMEZONE).date()
    state = discipline.load_state()
    random.seed(f"local-fallback-preview:{day.isoformat()}")
    lead = discipline.pick_lead(state, day)
    companion = discipline.pick_companion(lead, state, day)
    candidates = discipline.pick_echo_candidates(lead, companion, state, day)
    editorial, echo = discipline.fixed_editorial(lead, companion, candidates, day)
    page = discipline.build_html(lead, companion, echo, editorial, state, day, "fixed")
    validate_page(page, day)
    # Make linked assets portable in a file:// preview; production template stays unchanged.
    for name in ("practice.js", "jdb-site-navigation.js", "jdb-site-navigation.css"):
        page = page.replace(f'"/{name}"', f'"{(discipline.HERE / name).as_uri()}"')
        page = page.replace(f'"{name}"', f'"{(discipline.HERE / name).as_uri()}"')
    output.write_text(page, encoding="utf-8")
    print(f"Local preview: {output}; no AI call, state change, or publication.")


if __name__ == "__main__":
    main()
