import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("anthropic", types.SimpleNamespace())
import discipline_dashboard as discipline
from freshness import validate_page


DAY = datetime.date(2026, 10, 6)


def example():
    readings = []
    for source_id, passage_id in (("tao", "1"), ("epictetus", "I"), ("heraclitus", "10")):
        source = next(source for source in discipline.READING_SOURCES if source["id"] == source_id)
        readings.append({"source": source, "selection_key": f"{source_id}:{passage_id}",
                         "passage_id": passage_id, "passage_title": "A source title",
                         "passage_text": f"Unchanged public-domain source text from {source_id}."})
    editorial, echo = discipline.fixed_editorial(readings[0], readings[1], [readings[2]], DAY)
    return readings, editorial


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.readings, self.editorial = example()
        self.page = discipline.build_html(*self.readings, self.editorial, day=DAY, mode="fixed")

    def test_complete_fallback_is_fresh_and_disclosed(self):
        manifest = validate_page(self.page, DAY)
        self.assertEqual(manifest["editorial_mode"], "fixed")
        self.assertIn("fixed reflection prompts today", self.page)
        self.assertIn("Echo was not thematically matched", self.page)
        for reading in self.readings:
            self.assertIn(reading["passage_text"], self.page)

    def test_ai_mode_does_not_show_fallback_notice(self):
        page = discipline.build_html(*self.readings, self.editorial, day=DAY)
        self.assertEqual(validate_page(page, DAY)["editorial_mode"], "ai")
        self.assertNotIn('id="editorial-status"', page)

    def test_yesterday_date_is_not_fresh(self):
        with self.assertRaises(ValueError):
            validate_page(self.page, DAY + datetime.timedelta(days=1))

    def test_malformed_manifest_types_and_unlabelled_fallback_are_not_fresh(self):
        import re
        for payload in ([], {"version": True, "date": DAY.isoformat()},
                        {"version": 1, "date": DAY.isoformat(), "editorial_mode": "fixed", "selections": None}):
            changed = re.sub(r'(<script id="discipline-freshness" type="application/json">).*?(</script>)',
                             lambda match: match[1] + json.dumps(payload) + match[2], self.page, flags=re.S)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_page(changed, DAY)
        with self.assertRaises(ValueError):
            validate_page(self.page.replace('id="editorial-status"', ''), DAY)

    def test_missing_sections_and_empty_prompts_are_not_fresh(self):
        changes = (
            ('data-reading-role="echo"', 'data-reading-role="missing"'),
            ('data-selection-key="tao:1"', 'data-selection-key="tao:2"'),
            ('<dt>Surrender</dt>', '<dt>Missing</dt>'),
            ('<details class="return">', '<details class="missing">'),
            ('<details class="trail">', '<details class="missing">'),
            ('</body></html>', ''),
            (self.readings[0]["passage_text"], ''),
            (self.editorial["carry_question"], ''),
        )
        for original, replacement in changes:
            with self.subTest(original=original), self.assertRaises(ValueError):
                validate_page(self.page.replace(original, replacement), DAY)

    def test_missing_api_key_uses_fixed_without_calling_provider(self):
        with patch.object(discipline, "API_KEY", None), patch.object(discipline, "create_editorial") as provider:
            editorial, echo, mode = discipline.generate_editorial(*self.readings[:2], [self.readings[2]], DAY)
        provider.assert_not_called()
        self.assertEqual(mode, "fixed")
        self.assertEqual(echo["selection_key"], "heraclitus:10")
        self.assertTrue(editorial["daily_question"].endswith("?"))

    def test_two_provider_failures_fall_back_with_bounded_waits(self):
        with patch.object(discipline, "API_KEY", "test-only"), \
                patch.object(discipline.anthropic, "Anthropic", create=True) as factory, \
                patch.object(discipline, "create_editorial", side_effect=ValueError("invalid response")) as provider:
            _, _, mode = discipline.generate_editorial(*self.readings[:2], [self.readings[2]], DAY)
        self.assertEqual(mode, "fixed")
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(factory.call_args.kwargs["timeout"], 45.0)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 0)

    def test_missing_sdk_still_allows_fresh_fixed_readings(self):
        with patch.object(discipline, "API_KEY", "test-only"), patch.object(discipline, "anthropic", None):
            _, _, mode = discipline.generate_editorial(*self.readings[:2], [self.readings[2]], DAY)
        self.assertEqual(mode, "fixed")

    def test_valid_ai_editorial_keeps_ai_mode(self):
        with patch.object(discipline, "API_KEY", "test-only"), \
                patch.object(discipline.anthropic, "Anthropic", create=True), \
                patch.object(discipline, "create_editorial", return_value=dict(self.editorial)) as provider:
            _, _, mode = discipline.generate_editorial(*self.readings[:2], [self.readings[2]], DAY)
        self.assertEqual(mode, "ai")
        self.assertEqual(provider.call_count, 1)

    def test_gate_trusts_complete_page_not_date_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            output, state = Path(directory) / "index.html", Path(directory) / "state.json"
            state.write_text(json.dumps({"date": DAY.isoformat(), "morning": True}), encoding="utf-8")
            output.write_text("A stale incomplete page", encoding="utf-8")
            with patch.object(discipline, "OUTPUT_FILE", output), patch.object(discipline, "STATE_FILE", state), \
                    patch.dict(os.environ, {"RUN_NOW": "0", "EXPECTED_DATE": DAY.isoformat()}):
                discipline.gate(datetime.datetime(2026, 10, 6, 1, tzinfo=discipline.TIMEZONE))
                output.write_text(self.page, encoding="utf-8")
                with self.assertRaises(SystemExit) as skipped:
                    discipline.gate(datetime.datetime(2026, 10, 6, 1, tzinfo=discipline.TIMEZONE))
                self.assertEqual(skipped.exception.code, 0)
                # A deliberate human refresh retains its previous semantics.
                with patch.dict(os.environ, {"RUN_NOW": "1"}):
                    discipline.gate(datetime.datetime(2026, 10, 6, 1, tzinfo=discipline.TIMEZONE))

    def test_automatic_request_delayed_to_another_date_is_skipped(self):
        with patch.dict(os.environ, {"EXPECTED_DATE": "2026-10-05", "RUN_NOW": "0"}), \
                patch.object(discipline, "save_state") as save, self.assertRaises(SystemExit) as expired:
            discipline.gate(datetime.datetime(2026, 10, 6, 1, tzinfo=discipline.TIMEZONE))
        self.assertEqual(expired.exception.code, 0)
        save.assert_not_called()

    def test_gate_never_claims_success_before_rendering(self):
        with patch.dict(os.environ, {"EXPECTED_DATE": "", "RUN_NOW": "1"}), \
                patch.object(discipline, "save_state") as save:
            discipline.gate()
        save.assert_not_called()

    def test_real_local_fallback_build_and_repeated_noop_use_temporary_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output, state = Path(directory) / "index.html", Path(directory) / "state.json"
            with patch.object(discipline, "OUTPUT_FILE", output), patch.object(discipline, "STATE_FILE", state), \
                    patch.object(discipline, "API_KEY", None), \
                    patch.dict(os.environ, {"RUN_NOW": "0", "EXPECTED_DATE": ""}):
                discipline.main()
                today = datetime.datetime.now(discipline.TIMEZONE).date()
                manifest = validate_page(output.read_text(encoding="utf-8"), today)
                history = json.loads(state.read_text(encoding="utf-8"))
                self.assertEqual(history["date"], today.isoformat())
                self.assertEqual(manifest["selections"]["lead"], history["history"][-1]["lead"])
                before = output.read_bytes(), state.read_bytes()
                with self.assertRaises(SystemExit) as skipped:
                    discipline.main()
                self.assertEqual(skipped.exception.code, 0)
                self.assertEqual(before, (output.read_bytes(), state.read_bytes()))

    def test_invalid_output_preserves_previous_page_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output, state = Path(directory) / "index.html", Path(directory) / "state.json"
            output.write_text("previous page", encoding="utf-8")
            state.write_text('{"history": []}', encoding="utf-8")
            before = output.read_bytes(), state.read_bytes()
            with patch.object(discipline, "OUTPUT_FILE", output), patch.object(discipline, "STATE_FILE", state), \
                    patch.object(discipline, "API_KEY", None), patch.object(discipline, "build_html", return_value="partial"), \
                    patch.dict(os.environ, {"RUN_NOW": "1", "EXPECTED_DATE": ""}), self.assertRaises(ValueError):
                discipline.main()
            self.assertEqual(before, (output.read_bytes(), state.read_bytes()))

    @unittest.skipUnless(shutil.which("node"), "Node needed for cross-language contract test")
    def test_worker_accepts_actual_python_render_and_rejects_partial_render(self):
        code = '''import {inspectPage} from './scheduler/worker.mjs';
let input=''; for await(const chunk of process.stdin) input+=chunk;
const {page,date}=JSON.parse(input);
if(!inspectPage(page,date) || inspectPage(page.replace('<dt>Act</dt>','<dt>Missing</dt>'),date)) process.exit(1);'''
        completed = subprocess.run(["node", "--input-type=module", "-e", code],
            input=json.dumps({"page": self.page, "date": DAY.isoformat()}), text=True,
            cwd=discipline.HERE, capture_output=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
