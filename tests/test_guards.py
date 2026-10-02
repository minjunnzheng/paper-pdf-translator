"""Offline checks of term protection, guards and settings. No model request is sent."""

import json
import subprocess
import tempfile
import tomllib
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


BODY = "A closing paragraph of the main text that must still be translated."
CITED = "Doe, J. and Roe, R. (2001) An invented study of nothing. Journal of Examples 1, 1-10."


class References(unittest.TestCase):
    def make_pdf(self, folder: str, heading: str | None) -> Path:
        import fitz

        document = fitz.open()
        document.new_page().insert_text(
            (72, 100), "The opening page of the made-up paper."
        )
        page = document.new_page()
        page.insert_text((72, 100), BODY)
        if heading:
            page.insert_text((72, 200), heading)
        page.insert_text((72, 230), CITED)
        path = Path(folder) / "paper.pdf"
        document.save(path)
        return path

    def section(self, heading: str | None) -> dict | None:
        with tempfile.TemporaryDirectory() as folder:
            return pt.reference_section(self.make_pdf(folder, heading))

    def test_finds_the_section(self):
        for heading in (
            "References",
            "REFERENCES",
            "7. References",
            "Literature Cited",
        ):
            section = self.section(heading)
            self.assertEqual(section["heading_page"], 2, heading)
            self.assertTrue(pt.in_references(section, CITED))
            self.assertTrue(
                pt.in_references(
                    section, "Doe, J. and Roe, R. {v1}(2001) An invented study"
                )
            )
            self.assertFalse(pt.in_references(section, BODY))
            self.assertFalse(pt.in_references(section, heading))

    def test_no_heading(self):
        self.assertIsNone(self.section(None))
        self.assertFalse(pt.in_references(None, CITED))

    def translator(self, section, calls):
        def chat(system, user):
            calls.append(user)
            rows = json.loads(user.partition(pt.BATCH_MARKER)[2])
            return json.dumps([{"id": row["id"], "output": "譯文"} for row in rows])

        settings = pt.pdf_settings(
            {"model": "test-model", "endpoint": pt.UNUSED_ENDPOINT}
        )
        return pt.reviewing_translator(settings, [], chat, False, False, section)

    def batch(self, *texts: str) -> str:
        rows = [{"id": i, "input": text} for i, text in enumerate(texts)]
        return "instructions\n" + pt.BATCH_MARKER + "\n" + json.dumps(rows)

    def test_mixed_batch_sends_only_the_body(self):
        section, calls = self.section("References"), []
        reply = self.translator(section, calls).do_llm_translate(
            self.batch(BODY, CITED)
        )
        self.assertEqual(
            json.loads(reply), [{"id": 0, "output": "譯文"}, {"id": 1, "output": CITED}]
        )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("Doe", calls[0])
        self.assertEqual(len(section["skipped"]), 1)

    def test_reference_only_batch_sends_nothing(self):
        section, calls = self.section("References"), []
        translator = self.translator(section, calls)
        reply = translator.do_llm_translate(self.batch(CITED))
        self.assertEqual(json.loads(reply), [{"id": 0, "output": CITED}])
        # the engine's retry of an unchanged paragraph arrives wrapped in a prompt
        wrapped = "Long instructions.\nNow translate the following text:\n" + CITED
        self.assertEqual(translator.do_llm_translate(wrapped), CITED)
        self.assertEqual(translator.do_translate(wrapped), CITED)
        self.assertEqual(translator.do_translate(CITED), CITED)
        self.assertEqual(calls, [])
        self.assertEqual(len(section["skipped"]), 1)

    def test_without_a_section_everything_is_sent(self):
        calls = []
        reply = self.translator(None, calls).do_llm_translate(self.batch(BODY, CITED))
        self.assertEqual([row["output"] for row in json.loads(reply)], ["譯文", "譯文"])
        self.assertIn("Doe", calls[0])


class Plugin(unittest.TestCase):
    root = Path(__file__).resolve().parent.parent

    def test_manifests_match_the_package(self):
        version = tomllib.loads((self.root / "pyproject.toml").read_text())["project"][
            "version"
        ]
        for folder in (".codex-plugin", ".claude-plugin"):
            manifest = json.loads((self.root / folder / "plugin.json").read_text())
            self.assertEqual(manifest["name"], "paper-pdf-translator")
            self.assertEqual(manifest["version"], version)
        market = json.loads((self.root / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(market["plugins"][0]["source"], "./")
        skill = (self.root / "skills/paper-translate/SKILL.md").read_text()
        self.assertTrue(skill.startswith("---\nname: paper-translate\n"))
        self.assertIn(f"@v{version} ", skill)


if __name__ == "__main__":
    unittest.main()
