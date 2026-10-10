"""Testes do ponto de entrada (``src/pipeline.py``)."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))

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

    def test_without_a_client_and_without_no_model_it_refuses(self):
        code, _, err = self.run_main(str(self.document))
        self.assertEqual(code, pipeline.EXIT_ERROR)
        self.assertIn("--no-model", err)

    def test_an_injected_model_is_used(self):
        code, _, _ = self.run_main(
            str(self.document), "--out", str(self.out),
            generate=fake_model(item(1, "Ana Silva")))
        self.assertEqual(code, pipeline.EXIT_OK)
        masked = (self.out / pipeline.SUBMISSION_FILE).read_text("utf-8")
        self.assertEqual(masked.split("\n")[0], "Nome: * *")

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


if __name__ == "__main__":
    unittest.main()
