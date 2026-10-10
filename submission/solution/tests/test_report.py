"""Testes do relatório (``src/report.py``)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import report  # noqa: E402

NAME = {
    "line": 5,
    "text": "Maria Conceição Oliveira Santos",
    "category": "identificacao",
    "reason": "Nome completo da paciente.",
    "confidence": "certo",
}
HIV = {
    "line": 17,
    "text": "HIV positivo",
    "category": "saude",
    "reason": "Diagnóstico de saúde.",
    "confidence": "provavel",
}
EMAIL = {
    "line": 10,
    "text": "maria.santos@emailpessoal.pt",
    "category": "identificacao",
    "reason": "Endereço de email.",
    "confidence": "certo",
    "source": "regex",
}


class BuildReportTest(unittest.TestCase):
    def test_starts_with_title_and_ends_with_newline(self):
        text = report.build_report([NAME])
        self.assertTrue(text.startswith("# Relatório de anonimização"))
        self.assertTrue(text.endswith("\n"))

    def test_summary_counts(self):
        text = report.build_report([NAME, HIV, EMAIL])
        self.assertIn("- Itens ocultados: 3", text)
        self.assertIn("- Palavras nesses itens: 7", text)
        self.assertIn("| Identificação pessoal | 2 |", text)
        self.assertIn("| Saúde | 1 |", text)
        self.assertIn("| Regras de segurança | 1 |", text)
        self.assertIn("| Gemini | 2 |", text)

    def test_items_are_listed_by_line(self):
        text = report.build_report([HIV, NAME, EMAIL])
        first = text.index("Nome completo da paciente.")
        second = text.index("Endereço de email.")
        third = text.index("Diagnóstico de saúde.")
        self.assertLess(first, second)
        self.assertLess(second, third)

    def test_values_are_hidden_by_default(self):
        text = report.build_report([NAME, HIV, EMAIL])
        self.assertNotIn("Maria Conceição", text)
        self.assertNotIn("HIV positivo", text)
        self.assertNotIn("maria.santos@", text)
        self.assertNotIn("Valor original", text)

    def test_values_can_be_included(self):
        text = report.build_report([NAME], include_values=True)
        self.assertIn("Valor original", text)
        self.assertIn("Maria Conceição Oliveira Santos", text)

    def test_no_items(self):
        text = report.build_report([])
        self.assertIn("- Itens ocultados: 0", text)
        self.assertIn("Nenhum item foi ocultado.", text)

    def test_unknown_category_and_missing_fields(self):
        item = {"text": "algo", "category": "outra"}
        text = report.build_report([item])
        self.assertIn("outra", text)
        self.assertIn("desconhecida", text)

    def test_pipe_in_reason_is_escaped(self):
        item = dict(NAME, reason="a | b")
        text = report.build_report([item])
        self.assertIn("a \\| b", text)

    def test_does_not_change_the_input(self):
        items = [dict(NAME), dict(NAME, source="regex")]
        report.build_report(items)
        self.assertNotIn("sources", items[0])


class MergeItemsTest(unittest.TestCase):
    def test_same_text_and_line_is_merged(self):
        regex_name = dict(NAME, source="regex", confidence="provavel")
        merged = report.merge_items([NAME, regex_name])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["sources"], ["gemini", "regex"])

    def test_highest_confidence_is_kept(self):
        unsure = dict(NAME, confidence="incerto")
        merged = report.merge_items([unsure, NAME])
        self.assertEqual(merged[0]["confidence"], "certo")

    def test_same_text_on_other_line_is_kept(self):
        other = dict(NAME, line=20)
        self.assertEqual(len(report.merge_items([NAME, other])), 2)

    def test_items_without_line_go_last(self):
        no_line = {"text": "x", "category": "saude"}
        merged = report.merge_items([no_line, NAME])
        self.assertEqual(merged[0]["text"], NAME["text"])


class WarningsTest(unittest.TestCase):
    WARNING = {
        "line": 7,
        "text": "texto inexistente",
        "problem": "não encontrado no documento",
    }

    def test_warnings_section(self):
        text = report.build_report([NAME], warnings=[self.WARNING])
        self.assertIn("## Avisos", text)
        self.assertIn("linha 7", text)
        self.assertIn("não encontrado no documento", text)

    def test_warning_value_is_hidden_by_default(self):
        text = report.build_report([NAME], warnings=[self.WARNING])
        self.assertNotIn("texto inexistente", text)

    def test_warning_value_with_include_values(self):
        text = report.build_report(
            [NAME], warnings=[self.WARNING], include_values=True)
        self.assertIn("texto inexistente", text)

    def test_no_warnings_section_when_empty(self):
        self.assertNotIn("## Avisos", report.build_report([NAME]))

    def test_warning_without_line(self):
        warning = {"text": "x", "problem": "texto vazio"}
        text = report.build_report([], warnings=[warning])
        self.assertIn("sem linha", text)


if __name__ == "__main__":
    unittest.main()
