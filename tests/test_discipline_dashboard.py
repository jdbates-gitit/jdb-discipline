import datetime
import json
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("anthropic", types.SimpleNamespace())

import discipline_dashboard as discipline


class DisciplineGeneratorTests(unittest.TestCase):
    def test_four_day_lead_cycle_is_balanced(self):
        sources = [source for source in discipline.READING_SOURCES if source["lead"]]
        cycle_start_ordinal = 739500 - (739500 % len(sources))
        days = [datetime.date.fromordinal(cycle_start_ordinal + offset) for offset in range(4)]
        selected = [
            discipline.balanced_source_order(sources, day, "lead")[0]["id"]
            for day in days
        ]
        self.assertEqual(
            set(selected), {"tao", "chuangtzu", "epictetus", "brother_lawrence"}
        )

    def test_recent_reading_is_excluded_when_unused_options_exist(self):
        today = datetime.date(2026, 9, 20)
        state = {
            "history": [
                {"date": today.isoformat(), "lead": "tao:1", "companion": "", "echo": ""}
            ]
        }
        tao = next(source for source in discipline.READING_SOURCES if source["id"] == "tao")
        _, available = discipline.available_passage_ids(tao, state, today)
        self.assertNotIn("1", available)

    def test_brother_lawrence_library_has_all_conversations_and_letters(self):
        source = next(
            source for source in discipline.READING_SOURCES
            if source["id"] == "brother_lawrence"
        )
        readings = json.loads(source["file"].read_text(encoding="utf-8"))
        self.assertEqual(len(readings), 19)
        self.assertIn("conversation_4", readings)
        self.assertIn("letter_15", readings)

    def test_psalms_library_is_complete_and_preserves_known_reading(self):
        source = next(source for source in discipline.READING_SOURCES if source["id"] == "psalms")
        readings = discipline.load_source(source)
        self.assertEqual(set(readings), {str(number) for number in range(1, 151)})
        self.assertEqual(sum(len(entry["verses"]) for entry in readings.values()), 2461)
        self.assertEqual(len(readings["119"]["verses"]), 176)
        self.assertEqual(readings["23"]["verses"][0]["text"], "The LORD is my shepherd; I shall not want.")
        self.assertEqual(len(readings["23"]["verses"]), 6)
        self.assertNotIn("Project Gutenberg", readings["150"]["text"])

    def test_psalms_companion_on_half_of_days_without_repeating_recent_psalms(self):
        start = datetime.date(2026, 10, 3)
        state = {"history": []}
        leads, psalms = [], []
        for offset in range(56):
            day = start + datetime.timedelta(days=offset)
            lead = discipline.pick_lead(state, day)
            companion = discipline.pick_companion(lead, state, day)
            leads.append(lead["source"]["id"])
            self.assertNotEqual(lead["source"]["id"], companion["source"]["id"])
            if companion["source"]["id"] == "psalms":
                self.assertNotIn(companion["passage_id"], psalms)
                psalms.append(companion["passage_id"])
            else:
                candidates = discipline.pick_echo_candidates(lead, companion, state, day)
                self.assertEqual(sum(c["source"]["id"] == "psalms" for c in candidates), 8)
            state["history"].append({"date": day.isoformat(), "lead": lead["selection_key"], "companion": companion["selection_key"]})
        self.assertEqual(len(psalms), 28)
        self.assertEqual(leads.count("tao"), 14)

    def test_psalms_excerpts_preserve_complete_consecutive_verses(self):
        source = next(source for source in discipline.READING_SOURCES if source["id"] == "psalms")
        readings = discipline.load_source(source)
        for target in (discipline.EXCERPT_TARGET_CHARS, discipline.ECHO_TARGET_CHARS):
            for entry in readings.values():
                with patch.object(discipline.random, "choice", side_effect=lambda groups: groups[-1]) as choose:
                    excerpt, title = discipline.psalm_excerpt(entry, target)
                groups = choose.call_args.args[0]
                self.assertEqual([verse for group in groups for verse in group], entry["verses"])
                self.assertEqual(excerpt, "\n\n".join(verse["text"] for verse in groups[-1]))
                if len(groups) > 1:
                    self.assertIn("· excerpt", title)
                    self.assertIn(str(groups[-1][0]["number"]), title)
                else:
                    self.assertEqual(title, entry["title"])

    def test_editorial_validation_requires_questions_and_known_echo(self):
        echo = {
            "selection_key": "heraclitus:10",
            "source": {"label": "Heraclitus"},
        }
        result = {
            "daily_question": "What becomes possible when I meet this moment with trust?",
            "lead_lens": "A grounded lens.",
            "companion_note": "A distinct companion note.",
            "echo_key": "heraclitus:10",
            "echo_note": "A useful echo.",
            "confluence": "A confluence that preserves difference.",
            "carry_question": "What is the next honest and loving action available to me?",
        }
        validated, selected = discipline.validate_editorial(result, [echo])
        self.assertEqual(validated, result)
        self.assertEqual(selected, echo)

    def test_render_discloses_sources_rotation_and_ai_role(self):
        source = next(source for source in discipline.READING_SOURCES if source["id"] == "tao")
        reading = {
            "source": source,
            "passage_id": "1",
            "selection_key": "tao:1",
            "passage_title": "Chapter 1",
            "passage_text": "A source reading.",
        }
        editorial = {
            "daily_question": "What honest step can I take into this unfolding day?",
            "lead_lens": "A brief lead lens.",
            "companion_note": "A brief companion note.",
            "echo_key": "tao:1",
            "echo_note": "A brief echo note.",
            "confluence": "A confluence that names both meeting and difference.",
            "carry_question": "What loving action is available in the next moment?",
        }
        rendered = discipline.build_html(reading, reading, reading, editorial)
        self.assertIn("the Tao leads 25% of days", rendered)
        self.assertIn("Psalms is the companion every other day", rendered)
        self.assertIn("King James Version, public domain in the USA", rendered)
        self.assertIn("Anthropic Claude Haiku 4.5", rendered)
        self.assertIn("AI does not write, paraphrase, or alter the source readings", rendered)


if __name__ == "__main__":
    unittest.main()
