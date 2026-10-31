"""An open editorial map that can guide, never dictate, the reading search.

These are human-authored reading lenses, not claims that every author shares a
belief or that this list exhausts their works. A proposed theme starts the
search; the actual passages may open another lens or remain in disagreement.
"""
import datetime
import random

FAMILIES = {
    "attention": ("Attention & presence", "Seeing what is here before rushing to explain or change it."),
    "agency": ("Freedom & choice", "Judgment, responsibility, boundaries, and the next chosen response."),
    "change": ("Change & letting go", "Non-forcing, surrender, impermanence, and mortality without resignation."),
    "ethics": ("Love & conduct", "How kindness, compassion, generosity, and truth become actions."),
    "belonging": ("Belonging & relationship", "Friendship, equality, service, and shared life without erasing difference."),
    "wonder": ("Wonder & participation", "Nature, embodiment, ordinary beauty, joy, and entering the world."),
    "practice": ("Growth & practice", "Beginning again, patience, humility, and sustained effort without self-punishment."),
    "inner_life": ("Desire & difficult feelings", "Craving, sobriety, anger, grief, and the possibilities of an honest response."),
    "perspective": ("Perspective & paradox", "Uncertainty, contradiction, play, and solitude without easy resolution."),
    "meaning": ("Meaning & the sacred", "Gratitude, trust, integrity, and purpose while respecting distinct beliefs."),
}

# id, family, label, interpretive scope, one editorial fallback question.
# The AI writes an original reading-grounded question; it does not recite this bank.
_THEMES = (
    ("attention", "attention", "Attention", "The quality of noticing, listening, and meeting the ordinary.", "What deserves my undivided attention today that I usually hurry past?"),
    ("presence", "attention", "Presence", "Participation in this moment rather than living only in anticipation.", "Where might I actually arrive today instead of remaining busy with the next thing?"),
    ("stillness", "attention", "Stillness", "A receptive pause, not withdrawal from necessary action.", "What might I hear if I leave one ordinary moment unfilled today?"),
    ("clear_seeing", "attention", "Clear seeing", "Distinguishing what is present from the story added to it.", "What am I treating as a fact today that may only be my interpretation?"),
    ("judgment", "agency", "Judgment", "Examining impressions and opinions before consenting to them.", "Which opinion of mine deserves a second look before I act on it today?"),
    ("response", "agency", "Chosen response", "The space between an encounter and the conduct chosen within it.", "What response could I choose today that I would still respect tonight?"),
    ("boundaries", "agency", "Boundaries", "Care for self and others without confusing love with compliance.", "Where could a clear and kindly boundary make room for a more honest relationship today?"),
    ("courage", "agency", "Courage", "Acting responsibly with uncertainty or fear still present.", "What worthwhile step am I postponing until I feel more certain than life can promise?"),
    ("non_forcing", "change", "Non-forcing", "Skillful participation without coercing a person or a process.", "Where could I work with the conditions of this day instead of pushing harder against them?"),
    ("surrender", "change", "Surrender", "Releasing ownership of outcomes while remaining responsible; one lens among many.", "What result can I stop trying to own while still doing my part today?"),
    ("impermanence", "change", "Impermanence", "Changing conditions, relationships, selves, and opportunities.", "What changing part of my life might I meet with curiosity rather than treating it as a mistake?"),
    ("mortality", "change", "Mortality", "Finite time and loss as invitations to care, not demands for frantic achievement.", "What would I give real time to today if I remembered this day cannot be repeated?"),
    ("kindness", "ethics", "Kindness", "Small, concrete forms of considerate conduct.", "Who could experience a little more ease today because of how I choose to meet them?"),
    ("compassion", "ethics", "Compassion", "Recognizing suffering without making it an identity or a personal failure.", "Whose difficulty could I acknowledge today without rushing to fix, judge, or explain it?"),
    ("generosity", "ethics", "Generosity", "Giving time, attention, resources, or credit without buying an outcome.", "What could I give freely today without needing appreciation to make it worthwhile?"),
    ("truthfulness", "ethics", "Truthfulness", "Honest words and conduct without weaponizing honesty.", "What true thing could I say today with both clarity and care?"),
    ("belonging", "belonging", "Belonging", "A place in shared life that is not earned by flawless performance.", "Where could I participate today without first proving that I deserve a place?"),
    ("equality", "belonging", "Equal dignity", "Seeing people beyond roles, status, usefulness, or resemblance to oneself.", "Who am I reducing to a role today instead of meeting as a whole person?"),
    ("service", "belonging", "Service", "Useful contribution without control, martyrdom, or self-erasure.", "What useful thing could I do today without needing to become the center of it?"),
    ("friendship", "belonging", "Friendship", "Company, listening, mutual care, and allowing oneself to receive.", "Who might I reach toward today without waiting for the perfect reason or words?"),
    ("wonder", "wonder", "Wonder", "Encountering life as more than a problem or a resource.", "What ordinary part of this day might become surprising if I stop assuming I already know it?"),
    ("nature", "wonder", "Nature", "Encounter with the living world on its own terms, not merely as a metaphor.", "What could I notice outdoors today without needing it to improve or teach me anything?"),
    ("embodiment", "wonder", "Embodied life", "The body, senses, limits, and lived experience without shame or forced celebration.", "How could I listen to my body today without treating it as a project to correct?"),
    ("joy", "wonder", "Joy", "Pleasure, play, and appreciation that need not be postponed until life is solved.", "What small joy could I allow today without requiring every other part of life to be settled?"),
    ("begin_again", "practice", "Beginning again", "Renewal after error, discouragement, or a lost habit.", "What could I begin again today without turning the interruption into a verdict about myself?"),
    ("patience", "practice", "Patience", "Respecting time, process, and limits without tolerating avoidable harm.", "What needs steady care from me today rather than a demand for immediate progress?"),
    ("humility", "practice", "Humility", "Learning, admitting limits, and being corrected without humiliation.", "What might become possible today if I do not need to be the person who already knows?"),
    ("discipline", "practice", "Discipline", "Repeated worthwhile action rather than punishment or performance.", "Which small practice would make this day more honest even if nobody notices me doing it?"),
    ("craving", "inner_life", "Craving", "The pull of wanting, avoidance, and imagined completion.", "What am I asking one more purchase, achievement, or approval to finally settle for me?"),
    ("sobriety", "inner_life", "Sobriety", "Recovery as lived honesty, support, and protecting one's next choice.", "What support or honest conversation would help me meet this day without escaping it?"),
    ("anger", "inner_life", "Anger", "Recognizing heat without feeding retaliation or denying legitimate hurt.", "What is my anger asking me to protect, and how could I respond without passing the hurt along?"),
    ("grief", "inner_life", "Grief", "Loss and love without a requirement to find a lesson or a quick resolution.", "What loss could I make room for today without insisting it should already hurt less?"),
    ("uncertainty", "perspective", "Uncertainty", "Living and choosing without complete knowledge.", "What could I remain open to today without pretending I know how it will unfold?"),
    ("paradox", "perspective", "Paradox", "Holding competing truths without flattening them into a slogan.", "Which two honest things in my life seem opposed, and could I let both stay in view today?"),
    ("play", "perspective", "Play & freedom", "Experiment, humor, and loosening rigid identities.", "Where could I try something lightly today instead of demanding that it prove who I am?"),
    ("solitude", "perspective", "Solitude", "Being alone, listening inwardly, and distinguishing solitude from isolation.", "What kind of company or quiet would genuinely nourish me today rather than simply distract me?"),
    ("gratitude", "meaning", "Gratitude", "Recognizing what sustains life without denying suffering.", "What is sustaining me today that I have started treating as merely ordinary?"),
    ("trust", "meaning", "Trust & the sacred", "Faith, mystery, and relationship with God where personally meaningful; not a doctrine shared by all authors.", "Where could I meet the unknown with honest trust today without abandoning discernment?"),
    ("integrity", "meaning", "Integrity", "Alignment between conduct, commitments, and what one says matters.", "Where could my actions today quietly agree with what I say matters most?"),
    ("purpose", "meaning", "Purpose & contribution", "Participation in a larger life without demanding one final explanation.", "What contribution is available to me today before I solve the larger question of my purpose?"),
)
THEMES = tuple(dict(zip(("id", "family", "label", "summary", "question"), theme)) for theme in _THEMES)
THEMES_BY_ID = {theme["id"]: theme for theme in THEMES}
OPEN_THEME = {"id": "open_reading", "family": "open", "label": "Reading-led discovery",
    "summary": "An unexpected thread actually present in the readings, including a disagreement or no shared theme.",
    "question": "What do these readings leave me curious enough to notice or try in my own life today?"}
QUESTION_STYLES = (
    ("notice", "Begin with a concrete thing I might notice today, not an abstract self-assessment."),
    ("experiment", "Invite a small experiment I can actually try today, without promising a result."),
    ("encounter", "Bring the question into a real encounter with a person, place, task, or living thing."),
    ("tension", "Allow two incompatible invitations to remain honestly in tension; do not manufacture a synthesis."),
    ("possibility", "Open a possibility, pleasure, curiosity, or contribution, not another inventory of personal faults."),
    ("honesty", "Ask one searching but humane question; no shame, diagnosis, or demand to resolve my life before breakfast."),
)


def question_plan(state, day=None):
    """Random menu from five families; history reduces repetition, not reading breadth."""
    day = day or datetime.date.today()
    recent_ids, recent_families, recent_questions = set(), [], set()
    for entry in sorted(state.get("history", []), key=lambda item: str(item.get("date", "")), reverse=True):
        try:
            age = (day - datetime.date.fromisoformat(entry["date"])).days
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= age < 14:
            continue
        recent_ids.add(entry.get("question_theme"))
        if entry.get("question_family"):
            recent_families.append(entry["question_family"])
        if entry.get("daily_question"):
            recent_questions.add(entry["daily_question"])
    families = [family for family in FAMILIES if family not in recent_families[:2]]
    options = []
    for family in random.sample(families, min(5, len(families))):
        pool = [theme for theme in THEMES if theme["family"] == family and theme["id"] not in recent_ids]
        if not pool:
            pool = [theme for theme in THEMES if theme["family"] == family]
        options.append(random.choice(pool))
    style_id, style = random.choice(QUESTION_STYLES)
    return {"options": options, "style_id": style_id, "style": style, "recent_questions": sorted(recent_questions)}


def fallback_practice(theme=None):
    theme = theme or OPEN_THEME
    return {
        "surrender_question": "What assumption, demand, or familiar habit could I set down long enough to explore this question honestly?",
        "daily_action": "I will choose one ordinary encounter today to try a response suggested by this question, then notice what happens.",
        "evening_question": "What did I notice or try today, and what remains honestly unresolved for me?",
    }
