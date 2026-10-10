"""Testes da extração (``src/pdf_extractor.py``)."""

import sys
import unittest
from pathlib import Path

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))

try:
    import pdf_extractor  # noqa: E402
except ImportError:  # o PyMuPDF não está instalado
    pdf_extractor = None

PDF = SOLUTION.parents[1] / "raw_data" / "document_to_anonymize.pdf"


@unittest.skipIf(pdf_extractor is None, "o PyMuPDF não está instalado")
class RemoveEmptyLinesTest(unittest.TestCase):
    def test_blank_and_whitespace_only_lines_are_dropped(self):
        text = "a\n\n  \nb\n\t\nc"
        self.assertEqual(pdf_extractor.remove_empty_lines(text), "a\nb\nc")

    def test_trailing_spaces_are_removed(self):
        text = "Data: 15 de abril \nNome: Rui  \n"
        self.assertEqual(
            pdf_extractor.remove_empty_lines(text),
            "Data: 15 de abril\nNome: Rui",
        )

    def test_leading_spaces_and_inner_spaces_are_kept(self):
        text = "  recuo\nduas  palavras"
        self.assertEqual(pdf_extractor.remove_empty_lines(text), text)

    def test_empty_text(self):
        for text in ("", "\n\n", "  \n \n"):
            self.assertEqual(pdf_extractor.remove_empty_lines(text), "")

    def test_no_final_newline(self):
        self.assertFalse(pdf_extractor.remove_empty_lines("a\nb\n").endswith(
            "\n"))


@unittest.skipIf(pdf_extractor is None, "o PyMuPDF não está instalado")
@unittest.skipUnless(PDF.exists(), "o documento do desafio não existe")
class ChallengeDocumentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = pdf_extractor.extract_and_prepare_text(str(PDF))
        cls.text = text
        cls.lines = text.split("\n")

    def test_no_blank_lines_and_no_trailing_spaces(self):
        self.assertTrue(all(line.strip() for line in self.lines))
        self.assertTrue(all(line == line.rstrip() for line in self.lines))

    def test_line_count(self):
        self.assertEqual(len(self.lines), 60)

    def test_punctuation_accents_and_symbols_are_preserved(self):
        for expected in (
            "Relatório de Admissão - Centro Médico Lisboa",
            "Nome: Maria Conceição Oliveira Santos",
            "Telefone: +351 912 345 678",
            "Rendimento anual declarado: €62.500",
            "Pressão arterial na admissão: 145/90 mmHg",
        ):
            self.assertIn(expected, self.text)


if __name__ == "__main__":
    unittest.main()
