"""Local inspection bundle. No AI call, production output write, or publication."""
import argparse
import datetime
import html
import json
import random
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discipline_dashboard as d
from freshness import validate_page

NAV = '''<aside class="preview-banner"><strong>LOCAL INSPECTION · NOT PUBLISHED</strong><p>Real source texts; sample commentary drafted for this review, not a Claude API result. No production changes or AI calls.</p><nav aria-label="Inspection examples"><a href="index.html">1 · Montaigne leads</a><a href="02-montaigne-echo.html">2 · Montaigne echoes</a><a href="03-fallback.html">3 · Actual fallback</a><a href="rotation.html">How the flow works</a><a href="landing-card.html">Landing card</a></nav></aside>'''
CSS = '''.preview-banner{border:1px solid #c4956a;background:#201a27;padding:20px;margin-top:24px;color:#f0ede8;font:14px/1.6 system-ui}.preview-banner strong{color:#e0b47f;letter-spacing:.12em;font-size:11px}.preview-banner p{margin:8px 0 14px}.preview-banner nav{display:flex;flex-wrap:wrap;gap:8px}.preview-banner a{border:1px solid #706278;border-radius:3px;padding:7px 10px;text-decoration:none;font:13px/1.4 system-ui;min-height:36px}.preview-banner a:hover,.preview-banner a:focus-visible{border-color:#e0b47f;outline:2px solid #e0b47f;outline-offset:2px}'''


def selection(source_id, key, target=1100, last=False, tail=None):
    source = next(s for s in d.READING_SOURCES if s["id"] == source_id)
    entry = d.load_source(source)[key]
    with patch.object(d.random, "choice", side_effect=lambda choices: choices[-1] if last else choices[0]):
        reading = d.passage_from_entry(source, key, entry, target)
    if tail:
        units = entry["units"][-tail:]
        reading["passage_text"] = " ".join(unit["text"] for unit in units)
        reading["passage_title"] = entry["essay"].title() + " · excerpt"
        reading["passage_reference"] = f"Book III · paragraph {entry['paragraph']} · sentences {units[0]['label']}–{units[-1]['label']}"
    return reading


def decorate(page):
    page = page.replace('<div class="wrap">', '<div class="wrap">' + NAV, 1)
    page = page.replace('</style>', CSS + '</style>', 1)
    return page


def simple_page(title, body):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>body{margin:0;background:#100e17;color:#f0ede8;font:17px/1.75 system-ui}main{max-width:900px;margin:auto;padding:0 24px 60px}h1,h2,h3{font-family:Georgia,serif;color:#e0b47f;line-height:1.2}h1{font-size:42px}a{color:inherit}li{margin:14px 0}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid #44374d}section{margin:40px 0}.jdb-build{display:grid;grid-template-columns:35px 1fr;gap:20px;padding:24px 0;text-decoration:none;border-block:1px solid #44374d}.jdb-tag,.jdb-idx{color:#e0b47f;font:12px monospace}.jdb-body h3{font-size:30px;margin:18px 0}.jdb-stack{display:flex;flex-wrap:wrap;gap:8px}.jdb-stack span{border:1px solid #706278;padding:5px 8px;font:12px monospace}.jdb-right{grid-column:2}.jdb-arrow{display:none}button{font:inherit}'+CSS+'</style></head><body><main>'+NAV+body+'</main></body></html>'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() or output == d.HERE or output in d.HERE.parents:
        parser.error("Choose a new preview directory, not an existing directory or repository")
    output.mkdir(parents=True)
    before = {p: p.read_bytes() for p in (d.OUTPUT_FILE, d.STATE_FILE)}
    day = datetime.datetime.now(d.TIMEZONE).date()
    for name in ("jdb-site-navigation.css", "jdb-site-navigation.js"):
        shutil.copyfile(d.HERE / name, output / name)
    practice = (d.HERE / "practice.js").read_text(encoding="utf-8")
    practice = practice.replace('daily-discipline.evening.v1.', 'daily-discipline.preview.montaigne.v1.')
    (output / "practice.js").write_text(practice, encoding="utf-8")

    lead = selection("montaigne", "b3_of_experience_p110", last=True, tail=2)
    companion = selection("whitman", "miracles")
    echo = selection("heraclitus", "10", 520)
    first = {
        "question_theme": "presence", "daily_question": "What part of today could I actually inhabit instead of treating it as something to get through?",
        "lead_lens": "Montaigne is not describing a perfectly empty mind. He admits that his thoughts leave the orchard for other concerns, then describes bringing them back to the walk. His dancing is not another technique to master. It is a small admission that life is already happening in an ordinary activity. I do not hear an instruction to deny a difficult thought or ignore something that needs attention. I hear room for a return without perfection: not never wandering, but noticing where I am and allowing this particular experience to have some of me.",
        "companion_note": "Whitman meets the ordinary with exuberance: streets, trees, company, water, and the sky become occasions for wonder. Montaigne returns to a particular walk; Whitman opens the field wider. Their temperaments differ. I can accept either invitation without needing to feel wonder on command or turn every ordinary moment into a spiritual achievement.",
        "echo_note": "Heraclitus complicates the invitation: looking carefully does not make the world fully transparent. Attention can leave mystery intact.",
        "confluence": "Montaigne brings mind and body back into the same lived moment. Whitman finds abundance where I might see routine. Heraclitus does not promise that closer attention will disclose everything. These are not one doctrine of presence. Together they leave a useful opening: I can participate in a moment without extracting its lesson, explaining its mystery, or demanding that it make me feel better. Today might contain an enjoyable encounter or a difficult one. Being present does not require either kind of experience to become something else before it deserves my attention.",
        "carry_question": "When am I physically here but mentally bargaining with a different moment?",
        "surrender_question": "Could I set down the demand that this moment justify itself before I give it my attention?",
        "daily_action": "During one walk, meal, or conversation today, I will put my phone away and return gently when my attention wanders.",
        "evening_question": "Where did I actually arrive today, and what did that moment contain that I had almost missed?",
    }
    readings1 = (lead, companion, echo)
    lead2 = selection("epictetus", "XVII")
    companion2 = selection("whitman", "myself_1")
    echo2 = selection("montaigne", "b3_of_managing_the_will_p26", 520)
    second = {
        "question_theme": "integrity", "daily_question": "How could I take one responsibility seriously today without turning the role into the whole of who I am?",
        "lead_lens": "Epictetus pictures a life as a part in a play: the assignment is not entirely mine, but the manner of playing it matters. His account of an assigned role is stronger than a modern invitation to choose any identity I want. I can let it question how I meet responsibilities I did not design, without treating unequal circumstances or preventable harm as things nobody should challenge. What remains mine today may be the honesty, care, or skill with which I take up a particular task.",
        "companion_note": "Whitman begins with his own embodied existence: breath, grass, shared atoms, and an invitation to accompany him. This is not the same account of duty that Epictetus offers. The poem keeps a role from filling the whole horizon. There is a living person here, related to other living people, not merely a function to perform.",
        "echo_note": "Montaigne warns against making a borrowed role into our entire substance. His suspicion of the mask can challenge, rather than merely endorse, the Stoic stage metaphor.",
        "confluence": "Epictetus asks how well I will play the part before me. Montaigne asks whether I have mistaken the part for my whole self. Whitman offers a more expansive, bodily beginning that cannot be reduced to either instruction. I do not have to choose between caring about a responsibility and having a life beyond it. Nor do these passages settle which roles are just or worth accepting. A modest experiment is available: do one task conscientiously, then allow the person behind the task to return to conversation, rest, curiosity, or play without having to earn that return through flawless performance.",
        "carry_question": "What happens to my voice and attention when I need a role to prove my worth?",
        "surrender_question": "What borrowed expectation could I loosen without abandoning the responsibility that genuinely belongs to me?",
        "daily_action": "I will finish one responsibility with care, then spend ten minutes doing something I enjoy without reviewing my performance.",
        "evening_question": "Where did I act with care today, and where did I remember that I am more than the role?",
    }
    for name, readings, editorial in (("index.html", readings1, first), ("02-montaigne-echo.html", (lead2, companion2, echo2), second)):
        editorial["echo_key"] = readings[2]["selection_key"]
        editorial, _ = d.validate_editorial(editorial, [readings[2]])
        page = d.build_html(*readings, editorial, {"history": []}, day, "fixed")
        page = re.sub(r'<p class="note-privacy" id="editorial-status">.*?</p>', '<p class="note-privacy" id="editorial-status">Sample editorial for inspection. Source words are preserved; this is not a live Claude generation.</p>', page, count=1)
        page = decorate(page)
        validate_page(page, day)
        (output / name).write_text(page, encoding="utf-8")

    random.seed("montaigne-local-fallback")
    plan = d.question_plan({}, day)
    plan["day_theme"] = random.choice(plan["options"])
    theme = plan["day_theme"]
    lead = d.pick_lead({}, day, theme)
    companion = d.pick_companion(lead, {}, day, theme)
    candidates = d.pick_echo_candidates(lead, companion, {}, day, theme)
    editorial, echo = d.fixed_editorial(lead, companion, candidates, day, plan)
    page = decorate(d.build_html(lead, companion, echo, editorial, {"history": []}, day, "fixed"))
    validate_page(page, day)
    (output / "03-fallback.html").write_text(page, encoding="utf-8")

    # Deterministic local simulation: not a forecast of production readings.
    state, counts, leads, rows = {"history": []}, Counter(), Counter(), []
    random.seed("montaigne-140-day-inspection")
    for offset in range(140):
        date = day + datetime.timedelta(days=offset)
        plan = d.question_plan(state, date)
        plan["day_theme"] = random.choice(plan["options"])
        theme = plan["day_theme"]
        lead = d.pick_lead(state, date, theme)
        companion = d.pick_companion(lead, state, date, theme)
        candidates = d.pick_echo_candidates(lead, companion, state, date, theme)
        editorial, echo = d.fixed_editorial(lead, companion, candidates, date, plan)
        editorial["selection_theme"] = theme["id"]
        counts.update(r["source"]["id"] for r in (lead, companion, echo))
        leads.update([lead["source"]["id"]])
        state["history"].append(d.history_entry(lead, companion, echo, editorial, date, "fixed"))
    for source in d.READING_SOURCES:
        rows.append(f'<tr><th scope="row">{html.escape(source["label"])}</th><td>{leads[source["id"]]}</td><td>{counts[source["id"]]}</td></tr>')
    body = '<h1>Seven voices. No home-field advantage.</h1><p>A local proposal for Daily Discipline. The daily page still has just a lead, a companion, and a short Echo—not seven daily readings.</p><ol><li>Draw a varied starting theme from the 40-lens foundation, reducing recent repeats.</li><li>Give less-used lead voices priority. All seven are eligible; Tao has no reserved percentage.</li><li>Use soft word hints to find fresh passages that may illuminate or challenge the theme. Montaigne also has curated theme tags.</li><li>Balance total exposure for companions and Echoes. No repeated author in one edition.</li><li>The editor reads the actual words: keep the proposed theme only if it fits. Allow a better-supported question, disagreement, or separate invitations.</li></ol><h2>140-day local simulation</h2><p>This tests the selection code, not the Claude service or tomorrow\'s actual page. 420 reading slots, three different voices per edition. Exact lead balance is shown for this uninterrupted simulation, not promised calendar percentages.</p><table><thead><tr><th>Voice</th><th>Lead days</th><th>All appearances</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><h2>What is unchanged</h2><p>One question; Notice, Surrender, Act; Return Tonight; the Seven-Day Trail; the 56-day fresh-passage preference; conditional Dhammapada attribution. No schedule changes, AI calls, commits, pushes, or deployments.</p><h2>Source integrity</h2><p>Montaigne: 43 curated prose selections, Charles Cotton translation, W. C. Hazlitt edition (1877), Project Gutenberg 3600. Excerpts use consecutive complete sentences, not rewritten modern English. Historical claims and religious differences are not treated as modern medical or universal spiritual advice.</p><p><a href="https://www.gutenberg.org/ebooks/3600">Inspect the Montaigne source edition ↗</a></p>'
    (output / "rotation.html").write_text(simple_page("Daily Discipline · Proposed rotation", body), encoding="utf-8")
    landing = (d.HERE.parent / "jdb-landing" / "index.html").read_text(encoding="utf-8")
    card = re.search(r'<a class="jdb-build" href="https://discipline\.jdb-builds\.com">.*?</a>', landing, re.S)[0]
    card = card.replace('href="https://discipline.jdb-builds.com"', 'href="index.html"').replace("Live · Daily", "Proposed · Local preview")
    (output / "landing-card.html").write_text(simple_page("Daily Discipline · Proposed landing card", '<h1>The matching landing card</h1><p>Exact proposed wording from the local JDB Builds source. This isolated card view is not a full homepage-layout test.</p>'+card), encoding="utf-8")
    (output / "simulation.json").write_text(json.dumps({"days": 140, "leads": leads, "all_appearances": counts}, indent=2), encoding="utf-8")
    if any(p.read_bytes() != content for p, content in before.items()):
        raise RuntimeError("Preview changed production output or history")
    print(f"Preview: {output / 'index.html'}")
    print(json.dumps({"leads": leads, "all_appearances": counts}))
    print("Production output/history unchanged. No AI call, commit, push, or deployment.")


if __name__ == "__main__":
    main()
