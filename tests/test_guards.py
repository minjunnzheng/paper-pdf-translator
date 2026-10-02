"""Offline checks of term protection, guards and settings. No model request is sent."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import paper_translate as pt


def terms(text: str) -> None:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "terms.txt"
        path.write_text(text, encoding="utf-8")
        pt.load_terms(path)


class Terms(unittest.TestCase):
    def tearDown(self):
        pt.load_terms(None)

    def test_file_format(self):
        terms(
            "# comment\nmass spectrometry\nPCR  # acronym\nenzyme | 酵母, 酶素\n\nenzyme\n"
        )
        self.assertEqual(pt.REVIEW_TERMS, ["mass spectrometry", "PCR", "enzyme"])
        self.assertEqual(pt.FORBIDDEN, {"enzyme": ("酵母", "酶素")})

    def test_missing_term(self):
        with self.assertRaises(ValueError):
            terms("| 譯法\n")

    def test_protect_and_restore(self):
        terms("mass spectrometry\nPCR\n")
        text = "Mass Spectrometry and PCR, not pcr {v1}"
        protected = pt.protect_terms(text)
        self.assertNotIn("PCR", protected)
        self.assertIn("pcr", protected)
        self.assertNotIn("Spectrometry", protected)
        self.assertEqual(
            pt.restore_terms(protected), "mass spectrometry and PCR, not pcr {v1}"
        )

    def test_rejoin_wrapped_term(self):
        terms("mass spectrometry\n")
        self.assertEqual(pt.normalize_terms("MASS SPECTRO- METRY"), "mass spectrometry")

    def test_counts(self):
        terms("enzyme\nPCR\n")
        self.assertEqual(
            pt.english_terms("Enzyme, enzyme, PCR, pcr"), {"enzyme": 2, "PCR": 1}
        )
        self.assertEqual(pt.english_terms("nothing here"), {})

    def test_no_terms_file(self):
        self.assertEqual(pt.protect_terms("plain text"), "plain text")
        self.assertEqual(pt.english_terms("plain text"), {})


class Guards(unittest.TestCase):
    def tearDown(self):
        pt.load_terms(None)

    def test_accepts_faithful_revision(self):
        pt.validate_revision(
            "We heated it to 350 {v1} twice.", "我們將其加熱至 350 {v1} 兩次。"
        )

    def test_rejects_changed_number_or_placeholder(self):
        for revised in ("我們將其加熱至 360 {v1}。", "我們將其加熱至 350。"):
            with self.assertRaises(ValueError):
                pt.validate_revision("We heated it to 350 {v1}.", revised)

    def test_rejects_lost_term(self):
        terms("enzyme\n")
        with self.assertRaises(ValueError):
            pt.validate_revision("The enzyme is active.", "這種酵素具有活性。")
        pt.validate_revision("The enzyme is active.", "enzyme 具有活性。")

    def test_rejects_listed_rendering(self):
        terms("enzyme | 酵母\n")
        with self.assertRaises(ValueError):
            pt.validate_revision("The enzyme is active.", "enzyme（酵母）具有活性。")

    def test_rejects_untranslated_prose(self):
        with self.assertRaises(ValueError):
            pt.validate_revision("This is a result.", "This is a result.")

    def test_batch_structure(self):
        original = [{"id": 0, "input": "It was 5."}, {"id": 1, "input": "It was 6."}]
        pt.validate_review_batch(
            original,
            [{"id": 0, "output": "結果是 5。"}, {"id": 1, "output": "結果是 6。"}],
        )
        with self.assertRaises(ValueError):
            pt.validate_review_batch(original, [{"id": 0, "output": "結果是 5。"}])


class Converter(unittest.TestCase):
    def test_simplified_to_traditional(self):
        try:
            pt.uconv()
        except RuntimeError:
            self.skipTest("ICU uconv is not installed")
        self.assertEqual(
            pt.traditional("在这种情况下 {v1} 0.2"), "在這種情況下 {v1} 0.2"
        )


class Settings(unittest.TestCase):
    def test_pages(self):
        self.assertEqual(pt.page_numbers("1-3,7", 10), [1, 2, 3, 7])
        self.assertEqual(pt.page_numbers(None, 3), [1, 2, 3])

    def test_local_model_requests_disable_presence_penalty(self):
        from pdf2zh_next.translator import get_rate_limiter
        from pdf2zh_next.translator.translator_impl.openai import OpenAITranslator

        for penalty, expected in ((0, {"presence_penalty": 0}), (None, None)):
            config = {
                "model": "test-model",
                "endpoint": pt.UNUSED_ENDPOINT,
                "presence_penalty": penalty,
            }
            translator = OpenAITranslator(pt.pdf_settings(config), get_rate_limiter(1))
            self.assertEqual(translator.options.get("extra_body"), expected)
            self.assertEqual(translator.options["temperature"], 0.0)

    def test_remote_tunnel_rejects_non_loopback_url(self):
        tunnel = pt.remote_tunnel("host", "http://example.com:8080/v1")
        with self.assertRaises(ValueError):
            tunnel.__enter__()


class Codex(unittest.TestCase):
    def run_with(self, reply: str, model: str) -> tuple[str, list[str]]:
        seen = {}

        def fake_run(command, **options):
            seen["command"], seen["input"] = command, options["input"]
            Path(command[command.index("-o") + 1]).write_text(reply, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(pt.subprocess, "run", fake_run):
            text = pt.codex_chat(model, "system text", "user text")
        self.assertEqual(seen["input"], "system text\n\nuser text")
        return text, seen["command"]

    def test_reply_and_default_model(self):
        text, command = self.run_with('```json\n[{"id": 0}]\n```\n', pt.CODEX_DEFAULT)
        self.assertEqual(text, '[{"id": 0}]')
        self.assertNotIn("-m", command)
        self.assertEqual(command[command.index("-s") + 1], "read-only")
        self.assertEqual(command[-1], "-")

    def test_named_model(self):
        _, command = self.run_with("譯文", "some-model")
        self.assertEqual(command[command.index("-m") + 1], "some-model")

    def test_empty_reply_is_an_error(self):
        with self.assertRaises(RuntimeError):
            self.run_with("", pt.CODEX_DEFAULT)

    def test_remote_host_needs_a_local_engine(self):
        for engine in ("claude", "codex"):
            code = pt.main(
                ["run", "--pdf", "x.pdf", "--engine", engine, "--remote-host", "host"]
            )
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
