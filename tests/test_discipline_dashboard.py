import datetime
import json
import sys
import types
import unittest

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
        self.assertIn("Anthropic Claude Haiku 4.5", rendered)
        self.assertIn("AI does not write, paraphrase, or alter the source readings", rendered)


if __name__ == "__main__":
    unittest.main()
