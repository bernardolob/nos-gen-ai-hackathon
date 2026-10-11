"""Testes do ponto de entrada (``src/pipeline.py``)."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))

from test_gateway import ORIGIN, FakeWorker  # noqa: E402

try:
    import pipeline  # noqa: E402
except ImportError:  # o PyMuPDF não está instalado
    pipeline = None

DOCUMENT = "Nome: Ana Silva\nNIF: 123456789\nCidade: Porto\n"


def fake_model(*items):
    """Um ``generate`` que devolve sempre os itens dados."""
    answer = json.dumps(list(items))
    return lambda system, content: answer


def item(line, text):
    return {"line": line, "text": text, "category": "identificacao",
            "reason": "nome", "confidence": "certo"}


@unittest.skipIf(pipeline is None, "o PyMuPDF não está instalado")
class RunTest(unittest.TestCase):
    LINES = DOCUMENT.strip().split("\n")

    def test_without_a_model_only_the_rules_apply(self):
        result = pipeline.run(self.LINES)
        self.assertEqual(
            result["masked"],
            ["Nome: Ana Silva", "NIF: *", "Cidade: Porto"])
        self.assertEqual(result["issues"], [])
        self.assertIn("# Relatório de anonimização", result["report"])

    def test_model_and_rules_are_combined(self):
        generate = fake_model(item(1, "Ana Silva"), item(3, "Porto"))
        result = pipeline.run(self.LINES, generate)
        self.assertEqual(
            result["masked"], ["Nome: * *", "NIF: *", "Cidade: *"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["issues"], [])

    def test_an_empty_answer_with_rule_items_gives_a_warning(self):
        result = pipeline.run(self.LINES, fake_model())
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("modelo", result["warnings"][0]["problem"])

    def test_an_unusable_answer_raises(self):
        with self.assertRaises(pipeline.detection.DetectionError):
            pipeline.run(self.LINES, lambda system, content: "isto não é JSON")

    def test_the_report_hides_values_by_default(self):
        result = pipeline.run(self.LINES)
        self.assertNotIn("123456789", result["report"])
        shown = pipeline.run(self.LINES, include_values=True)
        self.assertIn("123456789", shown["report"])

    def test_an_item_the_model_invents_becomes_a_warning(self):
        generate = fake_model(item(1, "Joana Inexistente"))
        result = pipeline.run(self.LINES, generate)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertEqual(result["masked"][0], "Nome: Ana Silva")


@unittest.skipIf(pipeline is None, "o PyMuPDF não está instalado")
class ReadInstructionsTest(unittest.TestCase):
    def test_blank_instructions_are_none(self):
        for blank in (None, "", "  \n "):
            self.assertIsNone(pipeline.read_instructions(blank))

    def test_text_is_trimmed(self):
        self.assertEqual(
            pipeline.read_instructions("  Mascara as datas.\n"),
            "Mascara as datas.")

    def test_a_file_is_read_as_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "instr.txt"
            path.write_text("Mascara também o centro.\n", encoding="utf-8")
            self.assertEqual(
                pipeline.read_instructions(path=path),
                "Mascara também o centro.")

    def test_too_long_instructions_are_refused_without_echoing_them(self):
        text = "segredo " * 400
        with self.assertRaises(ValueError) as caught:
            pipeline.read_instructions(text)
        self.assertNotIn("segredo", str(caught.exception))

    def test_the_limit_itself_is_allowed(self):
        text = "a" * pipeline.MAX_INSTRUCTIONS
        self.assertEqual(pipeline.read_instructions(text), text)


@unittest.skipIf(pipeline is None, "o PyMuPDF não está instalado")
class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.document = Path(self.tmp.name) / "doc.txt"
        self.document.write_text(DOCUMENT, encoding="utf-8")
        self.out = Path(self.tmp.name) / "out"

    def run_main(self, *args, generate=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = pipeline.main(list(args), generate=generate)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dry_run_writes_nothing(self):
        code, out, _ = self.run_main(str(self.document), "--no-model")
        self.assertEqual(code, pipeline.EXIT_OK)
        self.assertIn("itens mascarados: 1", out)
        self.assertFalse(self.out.exists())

    def test_out_writes_the_masked_document_and_the_report(self):
        code, _, _ = self.run_main(
            str(self.document), "--no-model", "--out", str(self.out))
        self.assertEqual(code, pipeline.EXIT_OK)
        masked = (self.out / pipeline.SUBMISSION_FILE).read_text("utf-8")
        self.assertEqual(masked, "Nome: Ana Silva\nNIF: *\nCidade: Porto")
        self.assertTrue((self.out / pipeline.REPORT_FILE).exists())

    def test_the_output_has_the_same_number_of_lines_and_no_blank_ones(self):
        self.run_main(str(self.document), "--no-model", "--out",
                      str(self.out))
        masked = (self.out / pipeline.SUBMISSION_FILE).read_text("utf-8")
        self.assertEqual(len(masked.split("\n")), 3)
        self.assertTrue(all(line.strip() for line in masked.split("\n")))

    def test_blank_lines_in_a_text_input_are_dropped(self):
        self.document.write_text(
            "Nome: Ana\n\n  \nNIF: 123456789\n", encoding="utf-8")
        self.run_main(str(self.document), "--no-model", "--out",
                      str(self.out))
        masked = (self.out / pipeline.SUBMISSION_FILE).read_text("utf-8")
        self.assertEqual(masked, "Nome: Ana\nNIF: *")

    def test_without_a_gateway_and_without_no_model_it_refuses(self):
        with mock.patch.dict(os.environ, clear=True):
            code, _, err = self.run_main(str(self.document))
        self.assertEqual(code, pipeline.EXIT_ERROR)
        self.assertIn("GEMINI_GATEWAY_URL", err)
        self.assertIn("--no-model", err)

    def test_the_gateway_from_the_environment_is_used(self):
        worker = FakeWorker()
        self.addCleanup(worker.stop)
        worker.reply = {
            "model": "m", "text": json.dumps([item(1, "Ana Silva")])}
        env = {"GEMINI_GATEWAY_URL": worker.url,
               "GEMINI_GATEWAY_ORIGIN": ORIGIN}
        if "SystemRoot" in os.environ:
            env["SystemRoot"] = os.environ["SystemRoot"]
        with mock.patch.dict(os.environ, env, clear=True):
            code, _, _ = self.run_main(
                str(self.document), "--out", str(self.out))
        self.assertEqual(code, pipeline.EXIT_OK)
        masked = (self.out / pipeline.SUBMISSION_FILE).read_text("utf-8")
        self.assertEqual(masked.split("\n")[0], "Nome: * *")
        prompt = worker.requests[0]["body"]["prompt"]
        self.assertIn("<document>", prompt)
        self.assertIn("[1] Nome: Ana Silva", prompt)

    def test_a_gateway_failure_is_an_error_and_writes_nothing(self):
        worker = FakeWorker()
        self.addCleanup(worker.stop)
        worker.script = [422]
        env = {"GEMINI_GATEWAY_URL": worker.url,
               "GEMINI_GATEWAY_ORIGIN": ORIGIN}
        if "SystemRoot" in os.environ:
            env["SystemRoot"] = os.environ["SystemRoot"]
        with mock.patch.dict(os.environ, env, clear=True):
            code, _, err = self.run_main(
                str(self.document), "--out", str(self.out))
        self.assertEqual(code, pipeline.EXIT_ERROR)
        self.assertIn("recusou", err)
        self.assertFalse(self.out.exists())

    def test_an_injected_model_is_used(self):
        code, _, _ = self.run_main(
            str(self.document), "--out", str(self.out),
            generate=fake_model(item(1, "Ana Silva")))
        self.assertEqual(code, pipeline.EXIT_OK)
        masked = (self.out / pipeline.SUBMISSION_FILE).read_text("utf-8")
        self.assertEqual(masked.split("\n")[0], "Nome: * *")

    def test_instructions_reach_the_model(self):
        seen = []

        def generate(system, content):
            seen.append(content)
            return "[]"
        code, _, _ = self.run_main(
            str(self.document), "--instructions", "Mascara as cidades.",
            generate=generate)
        self.assertEqual(code, pipeline.EXIT_OK)
        self.assertIn("<user_instructions>", seen[0])
        self.assertIn("Mascara as cidades.", seen[0])
        self.assertIn("WHAT to mask or unmask", seen[0])

    def test_instructions_can_come_from_a_file(self):
        seen = []

        def generate(system, content):
            seen.append(content)
            return "[]"
        file = Path(self.tmp.name) / "instr.txt"
        file.write_text("Mascara os hospitais.", encoding="utf-8")
        self.run_main(str(self.document), "--instructions-file", str(file),
                      generate=generate)
        self.assertIn("Mascara os hospitais.", seen[0])

    def test_both_instruction_options_together_are_a_usage_error(self):
        with self.assertRaises(SystemExit):
            self.run_main(str(self.document), "--no-model",
                          "--instructions", "a", "--instructions-file", "b")

    def test_too_long_instructions_are_an_error_and_nothing_is_sent(self):
        seen = []
        code, _, err = self.run_main(
            str(self.document), "--instructions", "x" * 5000,
            generate=lambda s, c: seen.append(c) or "[]")
        self.assertEqual(code, pipeline.EXIT_ERROR)
        self.assertIn("máximo", err)
        self.assertEqual(seen, [])

    def test_a_missing_instructions_file_is_an_error(self):
        code, _, _ = self.run_main(
            str(self.document), "--no-model",
            "--instructions-file", str(Path(self.tmp.name) / "nao.txt"))
        self.assertEqual(code, pipeline.EXIT_ERROR)

    def test_a_missing_file_is_an_error(self):
        code, _, err = self.run_main(
            str(Path(self.tmp.name) / "nada.pdf"), "--no-model")
        self.assertEqual(code, pipeline.EXIT_ERROR)
        self.assertIn("não existe", err)

    def test_a_detection_failure_is_an_error_and_writes_nothing(self):
        code, _, err = self.run_main(
            str(self.document), "--out", str(self.out),
            generate=lambda system, content: "lixo")
        self.assertEqual(code, pipeline.EXIT_ERROR)
        self.assertIn("Erro", err)
        self.assertFalse(self.out.exists())

    def test_the_summary_never_shows_sensitive_values(self):
        _, out, err = self.run_main(str(self.document), "--no-model")
        self.assertNotIn("123456789", out + err)

    def test_use_cache_flag_invokes_cached_adapter(self):
        with mock.patch("gemini_adapter.make_cached_generate") as mock_cache:
            mock_cache.return_value = fake_model(item(1, "Ana Silva"))
            code, _, _ = self.run_main(
                str(self.document), "--use-cache", "--out", str(self.out)
            )
            self.assertEqual(code, pipeline.EXIT_OK)
            mock_cache.assert_called_once()

    def test_main_falls_back_to_gemini_adapter_when_gateway_absent(self):
        with mock.patch("gateway.from_env", return_value=None):
            with mock.patch("gemini_adapter.make_cached_generate") as mock_c:
                mock_c.return_value = fake_model(item(1, "Ana Silva"))
                code, _, _ = self.run_main(
                    str(self.document), "--out", str(self.out)
                )
                self.assertEqual(code, pipeline.EXIT_OK)
                mock_c.assert_called_once()


if __name__ == "__main__":
    unittest.main()
