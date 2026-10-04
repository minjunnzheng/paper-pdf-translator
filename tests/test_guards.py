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

    def test_ordinals_written_as_digits(self):
        source = "The first-order and second-order regions differ."
        pt.validate_revision(source, "1차 영역과 2차 영역은 다르다.", "en", "ko")
        pt.validate_revision(source, "1次領域と2次領域は異なる。", "en", "ja")
        pt.validate_revision(
            "The two previous studies agree.", "2つの先行研究は一致する。", "en", "ja"
        )
        for revised in (
            "1차 영역과 3차 영역은 다르다.",
            "1차와 1차와 2차 영역은 다르다.",
        ):
            with self.assertRaises(ValueError):
                pt.validate_revision(source, revised, "en", "ko")
        pt.validate_revision(  # one word each for 1 and 2, counted together
            "One sample showed the first and second peaks.",
            "1つの試料は1番目と2番目のピークを示した。",
            "en",
            "ja",
        )
        with self.assertRaises(ValueError):  # a number in the source must still survive
            pt.validate_revision("The first 350 samples.", "1번째 샘플.", "en", "ko")
        with self.assertRaises(ValueError):  # only English ordinal words are recognised
            pt.validate_revision(
                "Die erste Probe war rot.", "1번째 샘플은 붉었다.", "de", "ko"
            )

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


class Pages(unittest.TestCase):
    def make_job(self, folder: str) -> Path:
        import fitz

        document = fitz.open()
        first = document.new_page()
        first.insert_text(
            (72, 120), "The ratio fell steadily as the sample was heated."
        )
        second = document.new_page()
        second.insert_text((72, 120), BODY)
        second.insert_text((72, 200), "References")
        second.insert_text((72, 230), CITED)
        source = Path(folder) / "paper.pdf"
        document.save(source)
        paragraphs, skipped, heading = pt.pdf_paragraphs(source, [1, 2], True)
        self.assertEqual(heading, 2)
        self.assertIn("references", [s["reason"] for s in skipped])
        self.assertFalse(any("Doe" in p["source"] for p in paragraphs))
        for row in paragraphs:
            row.update(output="譯文<b>&", checks="passed")
        job = Path(folder) / "job"
        job.mkdir()
        page = pt.page_pair_html(
            "t <x>",
            paragraphs,
            pt.page_images(source, [1, 2]),
            heading,
            [("k", "v & w")],
        )
        (job / "translated.html").write_text(page)
        (job / "review.json").write_text(json.dumps(paragraphs, ensure_ascii=False))
        (job / "manifest.json").write_text(
            json.dumps({"source": str(source), "selected_source_pages": [1, 2]})
        )
        return job

    def test_page_html(self):
        with tempfile.TemporaryDirectory() as folder:
            page = (self.make_job(folder) / "translated.html").read_text()
        self.assertEqual(page.count('<section class="page"'), 2)
        self.assertEqual(page.count("data:image/jpeg;base64,"), 2)
        self.assertIn("譯文&lt;b&gt;&amp;", page)
        self.assertIn("t &lt;x&gt;", page)
        self.assertIn("參考文獻保留原文", page)
        self.assertNotIn("http://", page.split("<script>")[0])

    def test_figure_words_and_positions(self):
        import fitz

        with tempfile.TemporaryDirectory() as folder:
            document = fitz.open()
            page = document.new_page()
            body = (
                "A long body sentence that sets the usual size of the main text here."
            )
            for y in (100, 300, 500, 700):
                page.insert_text((72, y), body, fontsize=10)
            page.insert_text((72, 150), "SAMPLE PREPARATION", fontsize=10)
            page.insert_text((300, 400), "Metasediments", fontsize=6)
            page.insert_text(
                (72, 600), "x" * 30 + " " + "y" * 30 + " " + "z" * 30, fontsize=6
            )
            source = Path(folder) / "paper.pdf"
            document.save(source)
            rows, _, _ = pt.pdf_paragraphs(source, [1], False)
        label = {r["source"]: r for r in rows}
        self.assertEqual(label["SAMPLE PREPARATION"]["label"], "title")
        self.assertEqual(label["Metasediments"]["label"], "figure_text")
        self.assertNotIn("checks", label["Metasediments"])
        long = next(r for r in rows if r["source"].startswith("xxx"))
        self.assertEqual(
            (long["label"], long["checks"]), ("figure_text", "not translated")
        )
        self.assertTrue(all(r["label"] == "text" for r in rows if r["source"] == body))
        left, top, width, height = label["Metasediments"]["box"]
        self.assertAlmostEqual(left, 100 * 300 / 595, delta=1)
        self.assertTrue(0 < top < 100 and 0 < width < 100 and 0 < height < 5)

    def test_figure_words_on_the_page(self):
        rows = [
            {
                "id": 0,
                "page": 1,
                "label": "text",
                "box": [10, 10, 50, 5],
                "output": "正文",
                "checks": "passed",
                "source": "Body",
            },
            {
                "id": 1,
                "page": 1,
                "label": "figure_text",
                "box": [60, 40, 10, 2],
                "output": "變質沉積岩",
                "checks": "passed",
                "source": "Metasediments",
            },
            {
                "id": 2,
                "page": 1,
                "label": "figure_text",
                "box": [5, 70, 80, 10],
                "output": "",
                "checks": "not translated",
                "source": "x" * 200,
            },
        ]
        page = pt.page_pair_html("t", rows, {1: b"jpeg"}, None, [])
        self.assertIn("圖表內的文字（2 項）", page)
        self.assertIn('data-box="60,40,10,2"', page)
        self.assertIn("表格內容請看原文頁", page)
        self.assertIn('<div class="box" hidden></div>', page)
        self.assertNotIn("檢查未過", page)

    def test_reply_with_trailing_remark(self):
        reply = '[{"id": 3, "output": "譯文"}]\n\nNote: kept the units.'
        self.assertEqual(pt.parse_rows(reply, [3]), {3: "譯文"})
        with self.assertRaises(ValueError):
            pt.parse_rows("no array here", [3])

    def test_paragraph_batch(self):
        rows = [
            {"id": 0, "source": "It was 5 units."},
            {"id": 1, "source": "It was 6."},
        ]

        def chat(system, user):
            data = json.loads(user)
            items = data if isinstance(data, list) else data["draft"]
            return json.dumps(
                [
                    {
                        "id": r["id"],
                        "output": "結果是 " + ("5" if r["id"] == 0 else "7") + "。",
                    }
                    for r in items
                ]
            )

        try:
            pt.uconv()
        except RuntimeError:
            self.skipTest("ICU uconv is not installed")
        pt.translate_paragraphs(rows, chat, True)
        self.assertEqual(rows[0]["checks"], "passed")
        self.assertTrue(rows[1]["checks"].startswith("failed"))

    def test_server(self):
        import threading
        import urllib.error
        import urllib.request

        asked = []

        def chat(system, user):
            asked.append(user)
            return "回答。依據：第 2 頁"

        with tempfile.TemporaryDirectory() as folder:
            job = self.make_job(folder)
            server, token = pt.qa_server(
                job, chat, {"provider": "test", "model": "m"}, 0
            )
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_address[1]}"

            def call(path, body=None, token_value=token, host=None):
                headers = {"Content-Type": "application/json", "X-Token": token_value}
                if host:
                    headers["Host"] = host
                request = urllib.request.Request(
                    base + path,
                    json.dumps(body).encode() if body is not None else None,
                    headers,
                )
                try:
                    with urllib.request.urlopen(request, timeout=10) as reply:
                        return reply.status, reply.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()

            try:
                self.assertEqual(call("/")[0], 200)
                self.assertEqual(call("/", host="evil.example:80")[0], 403)
                self.assertEqual(call("/api/qa?t=wrong")[0], 403)
                self.assertEqual(call("/api/ask", {"question": "?"}, "wrong")[0], 403)
                status, body = call(
                    "/api/ask", {"question": "這段在講什麼？", "page": 2}
                )
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body)["answer"], "回答。依據：第 2 頁")
                self.assertIn("第 2 頁原文", asked[0])
                self.assertNotIn("第 1 頁原文", asked[0])
                status, _ = call(
                    "/api/ask", {"question": "全文呢？", "page": 2, "full": True}
                )
                self.assertIn("第 1 頁原文", asked[1])
                self.assertIn("先前的問答", asked[1])
                self.assertEqual(call("/api/ask", {"question": "", "page": 2})[0], 400)
                self.assertEqual(call("/api/ask", {"question": "?", "page": 9})[0], 400)
                status, body = call(f"/api/qa?t={token}")
                self.assertEqual(
                    [e["question"] for e in json.loads(body)],
                    ["這段在講什麼？", "全文呢？"],
                )
                self.assertEqual(len(json.loads((job / "qa.json").read_text())), 2)
            finally:
                server.shutdown()
                server.server_close()


JA = "この研究では、加熱実験によって試料の比率が段階的に低下することを確かめた。"
KO = "이 연구에서는 가열 실험을 통해 시료의 비율이 단계적으로 감소함을 확인하였다."
DE = "In dieser Studie wurde gezeigt, dass das Verhältnis beim Erhitzen schrittweise abnimmt."


class Languages(unittest.TestCase):
    def test_prompts(self):
        self.assertEqual(pt.translation_prompt("en", "zh-TW"), pt.PDF_PROMPT)
        self.assertEqual(pt.review_prompt("en", "zh-TW"), pt.REVIEW_PROMPT)
        prompt = pt.translation_prompt("ja", "zh-TW")
        self.assertIn("Japanese", prompt)
        self.assertIn("Traditional Chinese", prompt)
        self.assertIn("{v1}", pt.review_prompt("de", "zh-CN"))

    def test_untranslated_output_is_caught(self):
        cases = [
            ("ja", "zh-TW", JA, "本研究透過加熱實驗確認樣本的比例逐步下降。", JA),
            (
                "ja",
                "zh-TW",
                JA,
                "本研究透過加熱實驗確認樣本的比例逐步下降。",
                "本研究では加熱実験によって確かめた比例逐步下降。",
            ),
            ("ko", "zh-TW", KO, "本研究透過加熱實驗確認樣本的比例逐步下降。", KO),
            ("de", "zh-CN", DE, "本研究表明加热时比例逐步下降。", DE),
            (
                "en",
                "ja",
                "In this study the ratio fell step by step as the sample was heated.",
                "この研究では、加熱によって比率が段階的に低下した。",
                "In this study the ratio fell step by step as the sample was heated.",
            ),
            (
                "en",
                "fr",
                "In this study the ratio fell step by step as the sample was heated.",
                "Dans cette étude, le rapport a diminué progressivement.",
                "In this study the ratio fell step by step as the sample was heated.",
            ),
        ]
        for source_lang, target_lang, source, good, bad in cases:
            pt.validate_revision(source, good, source_lang, target_lang)
            with self.assertRaises(ValueError, msg=(source_lang, target_lang, bad)):
                pt.validate_revision(source, bad, source_lang, target_lang)

    def test_script_conversion(self):
        try:
            pt.uconv()
        except RuntimeError:
            self.skipTest("ICU uconv is not installed")
        self.assertEqual(pt.convert_script("這種情況", "zh-CN"), "这种情况")
        self.assertEqual(pt.convert_script("这种情况", "zh-TW"), "這種情況")
        self.assertEqual(pt.convert_script("이 연구", "ko"), "이 연구")

    def test_other_scripts_are_extracted_and_headings_found(self):
        import fitz

        for font, body, heading in (
            ("japan", JA, "参考文献"),
            ("korea", KO, "참고문헌"),
        ):
            with tempfile.TemporaryDirectory() as folder:
                document = fitz.open()
                page = document.new_page()
                for y in (100, 140, 180):
                    page.insert_text((72, y), body[:30], fontname=font, fontsize=10)
                page.insert_text((72, 300), heading, fontname=font, fontsize=10)
                page.insert_text((72, 330), body[:30], fontname=font, fontsize=10)
                source = Path(folder) / "paper.pdf"
                document.save(source)
                rows, skipped, found = pt.pdf_paragraphs(source, [1], True)
            self.assertEqual(found, 1, font)
            self.assertTrue(rows, font)
            self.assertNotIn("no words", [s["reason"] for s in skipped], font)
            self.assertIn("references", [s["reason"] for s in skipped], font)

    def test_other_languages_need_the_page_format(self):
        for options in (["--to", "zh-CN"], ["--from", "ja"]):
            self.assertEqual(
                pt.main(["run", "--pdf", "x.pdf", "--engine", "claude", *options]), 2
            )
        self.assertEqual(
            pt.main(
                [
                    "run",
                    "--pdf",
                    "x.pdf",
                    "--format",
                    "pages",
                    "--from",
                    "ja",
                    "--to",
                    "ja",
                ]
            ),
            2,
        )


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
