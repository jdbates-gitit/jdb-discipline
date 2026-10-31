import datetime
import json
import random
import unittest
from collections import Counter
from unittest.mock import patch

import discipline_dashboard as discipline
from build_montaigne import parse
from question_foundation import THEMES_BY_ID
from reading_rotation import SELECTION_VERSION, THEME_HINTS, daily_history, fair_source_pool, theme_score


class MontaigneRotationTests(unittest.TestCase):
    day = datetime.date(2026, 10, 31)

    def test_every_lens_has_soft_hints(self):
        self.assertEqual(set(THEME_HINTS), set(THEMES_BY_ID))
        self.assertGreater(theme_score("friendship and conversation", THEMES_BY_ID["friendship"]), 0)
        self.assertEqual(theme_score("abcd efgh", THEMES_BY_ID["friendship"]), 0)

    def test_archive_preserves_complete_source_sentences_and_attribution(self):
        source = next(s for s in discipline.READING_SOURCES if s["id"] == "montaigne")
        payload = json.loads(source["file"].read_text(encoding="utf-8"))
        self.assertEqual(payload["_metadata"]["translator"], "Charles Cotton")
        self.assertEqual(payload["_metadata"]["reading_count"], 43)
        self.assertEqual(len(payload["_metadata"]["sha256"]), 64)
        for key, entry in payload["readings"].items():
            self.assertEqual(" ".join(u["text"] for u in entry["units"]), entry["text"])
            self.assertTrue(set(entry["themes"]) <= set(THEMES_BY_ID), key)
            self.assertNotIn("\ufffd", entry["text"])
            self.assertIn("#link", entry["source_url"])
        text = payload["readings"]["b3_of_experience_p110"]["text"]
        self.assertIn("When I dance, I dance; when I sleep, I sleep.", text)

    def test_parser_keeps_wording_and_marks_paragraph_origin(self):
        markup = '<h2>BOOK THE THIRD</h2><a id="essay"></a><h2>CHAPTER XIII—OF EXPERIENCE</h2><p>When I dance, I dance; when I sleep, I sleep.</p>'
        entry = parse(markup)["b3_of_experience_p1"]
        self.assertEqual(entry["text"], "When I dance, I dance; when I sleep, I sleep.")
        self.assertTrue(entry["source_url"].endswith("#essay"))

    def test_old_quota_and_future_entries_do_not_create_catchup_debt(self):
        sources = discipline.READING_SOURCES
        history = [{"date": self.day.isoformat(), "lead": "tao:1"},
                   {"date": "2026-11-30", "lead": "montaigne:any", "selection_version": SELECTION_VERSION}]
        self.assertEqual(len(fair_source_pool(sources, {"history": history}, self.day, "lead")), 7)

    def test_manual_reruns_count_only_the_latest_edition_per_day(self):
        history = [{"date": self.day.isoformat(), "lead": source + ":a", "selection_version": SELECTION_VERSION}
                   for source in ("tao", "montaigne")]
        self.assertEqual(len(daily_history({"history": history}, self.day)), 1)
        self.assertEqual(daily_history({"history": history}, self.day)[0]["lead"], "montaigne:a")

    def test_theme_search_prefers_matching_fresh_excerpt_without_changing_words(self):
        source = {"id": "test", "label": "Test"}
        entries = {"a": "Friendship and conversation nourish a friend.", "b": "A stone and a wall stand."}
        with patch.object(discipline, "available_passage_ids", return_value=(entries, list(entries))):
            reading = discipline.pick_passage(source, {}, 1000, self.day, THEMES_BY_ID["friendship"])
        self.assertEqual(reading["passage_id"], "a")
        self.assertEqual(reading["passage_text"], entries["a"])

    def test_simulated_140_day_rotation_has_no_starved_voice_or_same_day_duplicate(self):
        state, counts, leads = {"history": []}, Counter(), Counter()
        with patch.object(discipline, "random", random.Random(840)):
            for offset in range(140):
                day = self.day + datetime.timedelta(days=offset)
                plan = discipline.question_plan(state, day)
                plan["day_theme"] = plan["options"][0]
                theme = plan["day_theme"]
                lead = discipline.pick_lead(state, day, theme)
                companion = discipline.pick_companion(lead, state, day, theme)
                candidates = discipline.pick_echo_candidates(lead, companion, state, day, theme)
                # Even a persistently first-choice editor cannot bypass exposure balance.
                echo = candidates[0]
                ids = [r["source"]["id"] for r in (lead, companion, echo)]
                self.assertEqual(len(set(ids)), 3)
                counts.update(ids)
                leads.update(ids[:1])
                self.assertTrue(all(n <= 4 for n in Counter(c["source"]["id"] for c in candidates).values()))
                for reading in (lead, companion, echo):
                    self.assertNotIn(reading["passage_id"], discipline.recent_passage_ids(state, reading["source"]["id"], day))
                state["history"].append(discipline.history_entry(lead, companion, echo, day=day))
        self.assertEqual(set(leads.values()), {20})
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 3)

    def test_prompt_proposes_theme_without_forcing_author_agreement(self):
        lead = discipline.pick_lead({}, self.day)
        companion = discipline.pick_companion(lead, {}, self.day)
        candidates = discipline.pick_echo_candidates(lead, companion, {}, self.day)
        plan = discipline.question_plan({}, self.day)
        plan["day_theme"] = plan["options"][0]
        editorial, _ = discipline.fixed_editorial(lead, companion, candidates, self.day, plan)
        from types import SimpleNamespace
        client = SimpleNamespace(messages=SimpleNamespace(create=unittest.mock.Mock(
            return_value=SimpleNamespace(content=[SimpleNamespace(text=json.dumps(editorial))]))))
        discipline.create_editorial(client, lead, companion, candidates, plan)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("THEME-GUIDED, TEXT-LED", prompt)
        self.assertIn("depart from the proposed theme if unsupported", prompt)
        self.assertIn("Do not invent a common teaching", prompt)


if __name__ == "__main__":
    unittest.main()
