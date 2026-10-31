"""Theme hints and history balancing, not semantic claims about the authors.

Plain word stems are deliberately soft retrieval hints. They never exclude a
source or replace the editor's responsibility to read the actual passage.
"""
import datetime
import random
import re

SELECTION_VERSION = "seven-voices-theme-v1"
ROLES = ("lead", "companion", "echo")
THEME_HINTS = {
    "attention": "attention attend listen observ notice heed",
    "presence": "present moment now today walk dance",
    "stillness": "still quiet rest silence calm",
    "clear_seeing": "see sight appear illusion discern",
    "judgment": "judg opinion reason impression truth",
    "response": "choice choose action act conduct response",
    "boundaries": "bound limit own refuse liberty",
    "courage": "courage fear brave dare danger",
    "non_forcing": "force effort natural easy gently",
    "surrender": "yield let release resign relinquish",
    "impermanence": "change turn flux river pass decay",
    "mortality": "death die mortal life age finite",
    "kindness": "kind gentle care benign goodwill",
    "compassion": "compassion pity suffer mercy tender",
    "generosity": "give gift generous offer share",
    "truthfulness": "truth honest sincere lie false",
    "belonging": "belong together fellow company humanity",
    "equality": "equal common human dignity rank",
    "service": "serve help duty useful public",
    "friendship": "friend love company conversation companion",
    "wonder": "wonder miracle marvel astonish beauty",
    "nature": "nature tree earth bird grass sea sun",
    "embodiment": "body flesh senses bodily foot breath",
    "joy": "joy pleasure delight glad enjoy gay",
    "begin_again": "begin again renew learn amend",
    "patience": "patient time slow wait endure",
    "humility": "humble ignorant ignorance learn confess",
    "discipline": "practice habit train discipline conduct",
    "craving": "desire craving want appetite greed lust",
    "sobriety": "heed support habit temperance intoxication",
    "anger": "anger wrath hate quarrel revenge",
    "grief": "grief sorrow loss mourn tears",
    "uncertainty": "doubt uncertain know question ignorance",
    "paradox": "contrary opposite difference contradiction strife",
    "play": "play dance laugh game sport light",
    "solitude": "alone solitude retire quiet inward",
    "gratitude": "gratitude thank gift appreciate enjoy",
    "trust": "trust god sacred faith mystery divine",
    "integrity": "integrity honest conduct virtue sincere",
    "purpose": "purpose work life contribute calling useful",
}


def theme_score(text, theme, tags=()):
    """Count distinct hints, capped; repetition/longer text earns no extra weight."""
    if not theme:
        return 0
    theme_id = theme["id"]
    words = set(re.findall(r"[a-z]+", text.casefold()))
    hits = sum(any(word.startswith(stem) for word in words)
               for stem in THEME_HINTS.get(theme_id, "").split())
    return min(hits, 4) + (2 if theme_id in tags else 0)


def daily_history(state, day):
    """Count one final edition per valid day; old quota history isn't a new debt."""
    dates = {}
    for entry in state.get("history", []):
        try:
            entry_day = datetime.date.fromisoformat(entry["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if entry_day <= day:
            dates[entry_day] = entry
    return [entry for date, entry in sorted(dates.items())
            if entry.get("selection_version") == SELECTION_VERSION]


def fair_source_pool(sources, state, day, role):
    """Equal lead opportunity; balance total exposure for companion and Echo.

    Fairness is checked before theme ranking, so easy lexical matches cannot
    crowd another author out. There is no preferred author or calendar quota.
    """
    if not sources:
        return []
    entries = daily_history(state, day)
    counts = {source["id"]: 0 for source in sources}
    roles = ("lead",) if role == "lead" else ROLES
    for entry in entries:
        for counted_role in roles:
            source_id = str(entry.get(counted_role, "")).partition(":")[0]
            if source_id in counts:
                counts[source_id] += 1
    minimum = min(counts.values())
    pool = [source for source in sources if counts[source["id"]] == minimum]
    random.shuffle(pool)
    return pool
