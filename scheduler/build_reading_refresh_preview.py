"""Render clearly labelled, local-only editorial examples and the theme map.

No provider calls, no run_state/index writes, and no workflow or deployment.
The sample editorials are authored for review, not evidence of a live AI run.
"""
import argparse
import datetime
import html
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import discipline_dashboard as discipline
from freshness import validate_page

SAMPLES = (
    {
        "file": "01-response.html", "label": "A different response", "theme": "anger",
        "lead": ("dhammapada", "v4_6"), "companion": ("whitman", "open_road_1"), "echo": ("heraclitus", "43"),
        "editorial": {
            "daily_question": "What could I do with the energy of anger today that protects what matters without passing the hurt along?",
            "lead_lens": "These verses do not ask me to pretend I was not hurt. They question what happens when the story of the injury becomes something I keep rehearsing. The practical invitation is to interrupt retaliation, not to erase a boundary or excuse another person's conduct. The reminder of mortality changes the scale of a quarrel: my time is limited, and keeping a grievance alive is one possible use of it. I can take the injury seriously while asking whether my next response needs to resemble the one that wounded me.",
            "companion_note": "Whitman's road opens a different possibility: a life not organized entirely around the complaint. His confidence is not the Dhammapada's account of liberation, and I do not need to adopt his whole stance. I can hear an invitation to move into the day without treating movement as proof that the hurt never mattered.",
            "echo_note": "Heraclitus resists the wish that all strife disappear. That is a real challenge here, not a third vote for peace: conflict and retaliatory hatred are not necessarily the same thing.",
            "confluence": "The Dhammapada asks what might end the reproduction of hatred. Whitman turns toward a world larger than the grievance. Heraclitus questions whether a world without strife is even desirable or possible. These are not three versions of surrender. I can keep a necessary disagreement alive without making another person an enemy; I can also discover that a conflict needs action rather than another soothing interpretation. The useful question is not how to make all tension vanish, but what kind of participant I will be in the tension that is actually here.",
            "carry_question": "When I feel the urge to repeat an injury, what fact, need, or boundary still deserves my attention?",
            "surrender_question": "Could I set aside the demand to make someone feel my hurt without setting aside the boundary I need?",
            "daily_action": "In one difficult exchange today, I will state the issue clearly without adding a sentence designed mainly to wound.",
            "evening_question": "Where did I respond differently today, and where did an honest disagreement still need to remain?",
        },
    },
    {
        "file": "02-room-for-wonder.html", "label": "Room for wonder", "theme": "wonder",
        "lead": ("tao", "11"), "companion": ("whitman", "miracles"), "echo": ("dhammapada", "v100_102"),
        "editorial": {
            "daily_question": "What might I notice today if I leave one ordinary moment free from the need to make it useful?",
            "lead_lens": "The wheel, vessel, and room are useful partly because of the space they do not fill. This is not an instruction to make myself empty of feeling or ambition. It unsettles the assumption that adding more is always how something becomes worthwhile. A pause in a conversation may permit an answer I did not anticipate. Unscheduled time may allow an encounter I could not plan. Before I add another explanation, task, or judgment, I can notice what the unfilled space already makes possible.",
            "companion_note": "Whitman does not value the ordinary because it improves him. Streets, water, trees, company, and the sky are already astonishing. His abundance is different from the Tao chapter's attention to absence. One voice notices the opening; the other notices how much life is present. Neither requires me to turn the encounter into a lesson.",
            "echo_note": "The Dhammapada values a useful word over a mass of empty recitation. It offers a contrast to both simple silence and Whitman's exuberant many-voiced attention: what matters is what the encounter actually does.",
            "confluence": "The Tao chapter locates usefulness partly in what is absent. Whitman finds miracles in an abundance of ordinary particulars. The Dhammapada distinguishes meaningful speech from a large quantity of words. There is a connection here, but not a shared rule that less is always better: Whitman's poem is wonderfully full. I can let that difference keep the question alive. Today might ask for quiet, a careful word, or wholehearted participation. I do not have to know in advance which encounter will open the most room.",
            "carry_question": "What is present in this moment that I miss when I immediately turn it into a task?",
            "surrender_question": "What if I briefly set down the assumption that an experience must improve me before I can enjoy it?",
            "daily_action": "I will spend five unhurried minutes outside today without headphones, a photograph, or a task to complete.",
            "evening_question": "What surprised me today when I stopped deciding in advance what the moment was for?",
        },
    },
    {
        "file": "03-different-invitations.html", "label": "Different invitations", "theme": "paradox",
        "lead": ("epictetus", "XXVI"), "companion": ("whitman", "o_me_o_life"), "echo": ("dhammapada", "v119_121"),
        "editorial": {
            "daily_question": "Can I practice steadiness without using philosophy to hurry myself or someone else out of grief?",
            "lead_lens": "Epictetus asks me to examine a double standard: events can seem ordinary when they happen to someone else and unbearable when they happen to me. That observation can expose distance rather than wisdom in my easy advice. The passage moves from a broken cup to bereavement, and that leap deserves resistance as well as attention. I can learn to recognize shared vulnerability without concluding that a person's grief is merely an error to correct. The challenge is to bring greater honesty to my judgment, not to make myself or another person less human.",
            "companion_note": "Whitman's poem begins amid dissatisfaction and self-reproach. Its answer is not that suffering has been reasoned away: life continues, and participation remains possible. That differs from the exercise Epictetus proposes. I can feel the invitation to contribute without treating a useful contribution as a cure for loss.",
            "echo_note": "The Dhammapada explicitly allows that a good person may encounter difficult days. Its account of the ripening of deeds is a distinct Buddhist commitment, not a promise that good conduct purchases an easy life.",
            "confluence": "I do not hear one comfortable teaching here. Epictetus seeks consistency in my judgments; Whitman answers discouragement with the possibility of a contribution; the Dhammapada considers conduct and consequences across time. None gives me permission to diagnose someone else's suffering as a failure of character. Today I might hold several invitations without resolving them: examine the story I am telling, make one worthwhile contribution, and allow pain to remain pain. An honest Confluence can name those separate directions instead of forcing them into an agreement the passages have not earned.",
            "carry_question": "Am I listening to this person's experience, or reaching too quickly for an idea that makes me comfortable?",
            "surrender_question": "What answer could I stop insisting on so that another person's actual experience has room to be heard?",
            "daily_action": "When someone shares a difficulty today, I will ask what it has been like before offering advice or perspective.",
            "evening_question": "Where did I allow an honest feeling or disagreement to remain without treating it as something I had failed to solve?",
        },
    },
)


def reading(source_id, passage_id, day, target):
    source = next(source for source in discipline.READING_SOURCES if source["id"] == source_id)
    library = discipline.load_source(source)
    # A stable preview excerpt, not a change to production's random selection.
    with_first_group = source_id in ("whitman", "dhammapada")
    if with_first_group:
        from unittest.mock import patch
        with patch.object(discipline.random, "choice", side_effect=lambda groups: groups[0]):
            return discipline.passage_from_entry(source, passage_id, library[passage_id], target)
    return discipline.passage_from_entry(source, passage_id, library[passage_id], target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() or output == discipline.HERE or output in discipline.HERE.parents:
        parser.error("Choose a new preview directory, not a repository or existing directory.")
    output.mkdir(parents=True)
    day = datetime.datetime.now(discipline.TIMEZONE).date()
    before = {path: path.read_bytes() for path in (discipline.OUTPUT_FILE, discipline.STATE_FILE)}
    state = discipline.load_state()
    random.seed("reading-refresh-local-preview")
    links = '<nav class="preview-links" aria-label="Local preview examples">' + "".join(
        f'<a href="{sample["file"]}">{index + 1}. {html.escape(sample["label"])}</a>' for index, sample in enumerate(SAMPLES)
    ) + '<a href="foundation.html">40-lens foundation</a><a href="fallback.html">Actual fallback example</a></nav>'
    for sample in SAMPLES:
        lead = reading(*sample["lead"], day, 1100)
        companion = reading(*sample["companion"], day, 1100)
        echo = reading(*sample["echo"], day, 520)
        editorial = {**sample["editorial"], "echo_key": echo["selection_key"], "question_theme": sample["theme"]}
        editorial, _ = discipline.validate_editorial(editorial, [echo])
        page = discipline.build_html(lead, companion, echo, editorial, state, day, "fixed")
        page = page.replace('<p class="note-privacy" id="editorial-status">', '<p class="note-privacy" id="editorial-status">LOCAL PREVIEW — sample commentary drafted for review, not a Claude API result. No provider call or publication. </p><p class="note-privacy" hidden>')
        page = page.replace('<div class="wrap">', '<div class="wrap">' + links, 1)
        page = page.replace('</style>', '.preview-links{display:flex;flex-wrap:wrap;gap:8px;padding:18px 0;border-bottom:1px solid var(--line)}.preview-links a{font:12px/1.5 var(--body);padding:8px 10px;border:1px solid var(--line);border-radius:3px;color:var(--bright)}.preview-links a:hover{border-color:var(--brass)}</style>', 1)
        validate_page(page, day)
        for name in ("practice.js", "jdb-site-navigation.js", "jdb-site-navigation.css"):
            page = page.replace(f'"/{name}"', f'"{(discipline.HERE / name).as_uri()}"')
            page = page.replace(f'"{name}"', f'"{(discipline.HERE / name).as_uri()}"')
        (output / sample["file"]).write_text(page, encoding="utf-8")
    foundation = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Daily Discipline · Question Foundation · Local Preview</title><style>body{background:#100e17;color:#f0ede8;font:17px/1.7 system-ui,sans-serif;max-width:850px;margin:auto;padding:32px 24px}h1,h2,h3{color:#e0b47f}a{color:#e0b47f}li{margin:12px 0}section{padding:12px 0;border-top:1px solid #332c3d}summary{font-size:24px;padding:20px 0;cursor:pointer}.preview-links{display:flex;gap:14px;flex-wrap:wrap}</style>' + links + '<h1>Readings first. A wider question.</h1><p>LOCAL PREVIEW. This is a working summary of possible themes—not a claim to exhaust these texts, and never a filter on which passages can be read.</p><h2>The daily sequence</h2><ol><li>Choose the lead: Tao, Chuang Tzu, Epictetus, and Dhammapada each lead one day in four.</li><li>Choose a companion from the other voices and gather bounded Echo candidates. No theme filter and no Psalms preference.</li><li>Offer a random menu of five theme families and a varied question approach, reducing recent repeats.</li><li>The editor follows an actual passage: choose a fitting lens or reading-led discovery. The voices may agree, challenge each other, or remain independent.</li><li>Write a new question and a concrete daily practice. Keep theme metadata in public reading history for future variety. Exact recent AI question repeats are rejected.</li></ol><p>Surrender stays one practice step and one of 40 lenses. It does not govern every question, reading, action, or evening reflection. The six approaches vary noticing, experiment, encounter, tension, possibility, and honest inquiry.</p>' + discipline.build_foundation_html().replace('<details class="foundation">', '<details class="foundation" open>', 1) + '<h2>What each voice contributes</h2><p>Tao: non-forcing, humility, naturalness, useful absence, returning. Chuang Tzu: story, perspective, transformation, freedom, humor. Epictetus: impressions, chosen response, responsibility, limits. Dhammapada: conduct, heedfulness, craving, compassion, Buddhist liberation. Whitman: embodied life, belonging, equality, wonder, joy, grief, mortality. Heraclitus: change, strife, opposites, hidden order. These are editorial summaries, not interchangeable doctrines.</p><h2>Sample landing-card copy</h2><p>I built a daily practice for recovery, reflection, and spiritual growth. A fresh question opens a lead reading, a companion, and a brief Echo from Tao Te Ching, Chuang Tzu, Epictetus, Dhammapada, Walt Whitman, and Heraclitus. Tao leads one day in four. Readings come first; a broad, randomly varied question foundation invites connection, disagreement, or separate insights. Claude Haiku 4.5 normally writes the connective editorial without rewriting the source texts. Notice, Surrender, Act, Return Tonight, and the Seven-Day Trail carry the reading into the day. If AI is unavailable, fresh readings remain with clearly labelled reflection prompts.</p><p>Stack: Python · JavaScript · Claude Haiku 4.5 · GitHub Actions · Sourced Text Library · Cloudflare Pages.</p><p>No publication, no schedule change, no AI API call. The sample editions demonstrate editorial possibilities; the fallback example uses the actual no-AI generator path.</p></html>'
    (output / "foundation.html").write_text(foundation, encoding="utf-8")
    if any(path.read_bytes() != content for path, content in before.items()):
        raise RuntimeError("Preview must not change production index or run_state")
    print(f"Local preview: {output / SAMPLES[0]['file']}")
    print(f"Theme foundation: {output / 'foundation.html'}")
    print("Production index and history unchanged. Sample commentary only; no AI/provider call or publication.")


if __name__ == "__main__":
    main()
