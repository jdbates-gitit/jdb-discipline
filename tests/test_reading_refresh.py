import datetime
import json
import random
import re
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("anthropic", types.SimpleNamespace())
import discipline_dashboard as discipline
import question_foundation as foundation
import build_new_readings as builder


class ReadingRefreshTests(unittest.TestCase):
    day = datetime.date(2026, 10, 17)

    def test_archive_contains_all_423_dhammapada_verses_once(self):
        source = next(s for s in discipline.READING_SOURCES if s["id"] == "dhammapada")
        readings = discipline.load_source(source)
        numbers = [n for entry in readings.values() for unit in entry["units"] for n in unit["numbers"]]
        self.assertEqual(numbers, list(range(1, 424)))
        self.assertEqual(len(readings), 147)
        self.assertEqual(readings["v221_223"]["units"][-1]["text"],
            "Overcome the angry by non-anger; overcome the wicked by goodness; overcome the miser by generosity; overcome the liar by truth.")
        self.assertTrue(all(entry["source_url"].startswith(builder.DHAMMA_ROOT) for entry in readings.values()))
        archive = json.loads(source["file"].read_text(encoding="utf-8"))
        self.assertEqual(archive["_metadata"]["license"], builder.DHAMMA_LICENSE)

    def test_whitman_archive_preserves_sections_and_poetry(self):
        source = next(s for s in discipline.READING_SOURCES if s["id"] == "whitman")
        readings = discipline.load_source(source)
        self.assertEqual(len(readings), 53)
        self.assertEqual({entry["poem"] for entry in readings.values()}, set(builder.WHITMAN_SELECTIONS))
        self.assertNotIn("open_road_10", readings)
        self.assertTrue(readings["open_road_1"]["text"].startswith("Afoot and light-hearted I take to the open road,"))
        self.assertIn("That the powerful play goes on, and you may contribute a verse.", readings["o_me_o_life"]["text"])
        reading = discipline.passage_from_entry(source, "open_road_1", readings["open_road_1"])
        self.assertIn('white-space:pre-line', discipline.reading_paragraphs(reading))
        self.assertTrue(all("<pre" not in entry["text"] and "Project Gutenberg" not in entry["text"] for entry in readings.values()))

    def test_new_excerpts_are_complete_consecutive_units(self):
        for source in (s for s in discipline.READING_SOURCES if s.get("complete_units")):
            for key, entry in discipline.load_source(source).items():
                for target in (80, discipline.ECHO_TARGET_CHARS, discipline.EXCERPT_TARGET_CHARS):
                    with self.subTest(source=source["id"], key=key, target=target), \
                            patch.object(discipline.random, "choice", side_effect=lambda groups: groups[-1]) as choose:
                        reading = discipline.passage_from_entry(source, key, entry, target)
                        groups = choose.call_args.args[0]
                        self.assertEqual([unit for group in groups for unit in group], entry["units"])
                        self.assertEqual(reading["passage_text"], source.get("unit_separator", "\n\n").join(unit["text"] for unit in groups[-1]))
                        if len(groups) > 1:
                            self.assertIn("excerpt", reading["passage_title"])

    def test_foundation_has_40_distinct_lenses_across_ten_families(self):
        self.assertEqual(len(foundation.THEMES_BY_ID), 40)
        self.assertEqual(len(foundation.FAMILIES), 10)
        for family in foundation.FAMILIES:
            self.assertEqual(sum(t["family"] == family for t in foundation.THEMES), 4)
        for theme in foundation.THEMES:
            self.assertTrue(theme["summary"] and theme["question"].endswith("?"))
            self.assertTrue(6 <= len(theme["question"].split()) <= 40)

    def test_question_menu_varies_without_weekday_schedule(self):
        with patch.object(foundation, "random", random.Random(91)):
            plans = [foundation.question_plan({}, self.day) for _ in range(30)]
        offered = {theme["id"] for plan in plans for theme in plan["options"]}
        self.assertEqual(len(offered), 40)
        self.assertGreater(len({plan["style_id"] for plan in plans}), 4)
        for plan in plans:
            self.assertEqual(len({theme["family"] for theme in plan["options"]}), 5)

    def test_recent_themes_and_families_are_deprioritized(self):
        history = [{"date": "2026-10-16", "question_theme": "surrender", "question_family": "change", "daily_question": "A recent question?"},
                   {"date": "2026-10-15", "question_theme": "anger", "question_family": "inner_life"},
                   {"date": "2026-11-01", "question_theme": "joy", "question_family": "wonder"}]
        for _ in range(20):
            plan = foundation.question_plan({"history": history}, self.day)
            self.assertTrue(all(t["family"] not in {"change", "inner_life"} for t in plan["options"]))
            self.assertEqual(plan["recent_questions"], ["A recent question?"])

    def test_readings_never_depend_on_question_plan(self):
        with patch.object(discipline, "question_plan", side_effect=AssertionError("Reading selector consulted a theme")):
            lead = discipline.pick_lead({}, self.day)
            companion = discipline.pick_companion(lead, {}, self.day)
            self.assertTrue(discipline.pick_echo_candidates(lead, companion, {}, self.day))

    def test_history_balances_all_seven_leads_instead_of_reserving_tao(self):
        start = self.day
        leads, companions = [], []
        state = {"history": []}
        for offset in range(70):
            day = start + datetime.timedelta(days=offset)
            lead = discipline.pick_lead(state, day)
            companion = discipline.pick_companion(lead, state, day)
            echo = discipline.pick_echo_candidates(lead, companion, state, day)[0]
            leads.append(lead["source"]["id"])
            companions.append(companion["source"]["id"])
            state["history"].append(discipline.history_entry(lead, companion, echo, day=day))
        for source in discipline.READING_SOURCES:
            self.assertEqual(leads.count(source["id"]), 10)
        self.assertEqual(set(companions), {s["id"] for s in discipline.READING_SOURCES})

    def test_history_and_trail_keep_retired_authors_honestly(self):
        entries = [{"date": self.day.isoformat(), "lead": "brother_lawrence:letter_1", "companion": "psalms:23"}]
        rendered = discipline.build_trail_html(entries, self.day)
        self.assertIn("Brother Lawrence", rendered)
        self.assertIn("Psalms", rendered)
        self.assertNotIn("brother_lawrence", {source["id"] for source in discipline.READING_SOURCES})

    def test_fixed_questions_use_broad_random_menu_and_save_metadata(self):
        lead = discipline.pick_lead({}, self.day)
        companion = discipline.pick_companion(lead, {}, self.day)
        candidates = discipline.pick_echo_candidates(lead, companion, {}, self.day)
        questions, themes = set(), set()
        with patch.object(foundation, "random", random.Random(17)):
            for _ in range(40):
                plan = foundation.question_plan({}, self.day)
                editorial, echo = discipline.fixed_editorial(lead, companion, candidates, self.day, plan)
                questions.add(editorial["daily_question"])
                themes.add(editorial["question_theme"])
                entry = discipline.history_entry(lead, companion, echo, editorial, self.day, "fixed")
                self.assertEqual(entry["question_theme"], editorial["question_theme"])
                self.assertIn(entry["question_family"], foundation.FAMILIES)
        self.assertGreater(len(questions), 15)
        self.assertGreater(len(themes), 15)

    def test_unknown_lens_and_exact_recent_question_are_rejected(self):
        lead = discipline.pick_lead({}, self.day)
        companion = discipline.pick_companion(lead, {}, self.day)
        candidates = discipline.pick_echo_candidates(lead, companion, {}, self.day)
        plan = foundation.question_plan({}, self.day)
        editorial, _ = discipline.fixed_editorial(lead, companion, candidates, self.day, plan)
        with self.assertRaises(ValueError):
            discipline.validate_editorial({**editorial, "question_theme": "invented"}, candidates, plan)
        plan["recent_questions"] = [editorial["daily_question"].upper()]
        with self.assertRaises(ValueError):
            discipline.validate_editorial(dict(editorial), candidates, plan)

    def test_ai_prompt_allows_disagreement_and_open_discovery(self):
        lead = discipline.pick_lead({}, self.day)
        companion = discipline.pick_companion(lead, {}, self.day)
        candidates = discipline.pick_echo_candidates(lead, companion, {}, self.day)
        plan = foundation.question_plan({}, self.day)
        editorial, _ = discipline.fixed_editorial(lead, companion, candidates, self.day, plan)
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=unittest.mock.Mock(
            return_value=types.SimpleNamespace(content=[types.SimpleNamespace(text=json.dumps(editorial))]))))
        discipline.create_editorial(client, lead, companion, candidates, plan)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        for required in ("READINGS FIRST", "open_reading", "independent invitations", "not the theme of the whole day", "Do not invent a common teaching"):
            self.assertIn(required, prompt)

    def test_exhausted_authored_question_bank_does_not_fail_fresh_readings(self):
        lead = discipline.pick_lead({}, self.day)
        companion = discipline.pick_companion(lead, {}, self.day)
        candidates = discipline.pick_echo_candidates(lead, companion, {}, self.day)
        plan = foundation.question_plan({}, self.day)
        plan["recent_questions"] = [theme["question"] for theme in (*foundation.THEMES, foundation.OPEN_THEME)]
        editorial, _ = discipline.fixed_editorial(lead, companion, candidates, self.day, plan)
        self.assertEqual(editorial["question_theme"], "open_reading")


if __name__ == "__main__":
    unittest.main()
