"""Testes da verificação (``src/verification.py``)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import verification  # noqa: E402


class CompareLinesTest(unittest.TestCase):
    def test_no_issues_when_fully_masked(self):
        issues = verification.compare_lines(
            ["Nome: Maria Santos"], ["Nome: * *"]
        )
        self.assertEqual(issues, [])

    def test_no_issues_when_word_kept(self):
        issues = verification.compare_lines(
            ["Nome: Maria Santos"], ["Nome: Maria Santos"]
        )
        self.assertEqual(issues, [])

    def test_keeps_edge_punctuation(self):
        issues = verification.compare_lines(
            ["Filhos: 2 (João, 15 anos)"], ["Filhos: * (*, * *)"]
        )
        self.assertEqual(issues, [])

    def test_detects_partial_mask_as_unexpected_change(self):
        issues = verification.compare_lines(
            ["Nome: Maria Santos"], ["Nome: M* Santos"]
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "unexpected_word_change")
        self.assertEqual(issues[0]["original_word"], "Maria")

    def test_isolated_symbol_wrongly_masked_is_flagged(self):
        issues = verification.compare_lines(
            ["Admissão - Centro"], ["* * Centro"]
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["original_word"], "-")

    def test_detects_blank_line(self):
        issues = verification.compare_lines(
            ["Linha um", "Linha dois"], ["Linha um", ""]
        )
        types = [item["type"] for item in issues]
        self.assertIn("blank_line", types)

    def test_detects_word_count_mismatch(self):
        issues = verification.compare_lines(
            ["Nome: Maria Santos"], ["Nome: *"]
        )
        self.assertEqual(issues[0]["type"], "word_count_mismatch")

    def test_detects_line_count_mismatch(self):
        issues = verification.compare_lines(
            ["Linha um", "Linha dois"], ["Linha um"]
        )
        self.assertEqual(issues[0]["type"], "line_count_mismatch")


class JoinedWordsTest(unittest.TestCase):
    """Casos que o masking.py separa sem espaço (ver MASKING.md)."""

    def test_comma_without_space_is_not_flagged(self):
        issues = verification.compare_lines(
            ["Filhos: João,Ana"], ["Filhos: *,*"]
        )
        self.assertEqual(issues, [])

    def test_semicolon_without_space_is_not_flagged(self):
        issues = verification.compare_lines(
            ["Contactos: Rui;Ana;Rita"], ["Contactos: *;*;*"]
        )
        self.assertEqual(issues, [])

    def test_slash_between_words_is_not_flagged(self):
        issues = verification.compare_lines(
            ["Pessoas: Rui/Ana"], ["Pessoas: */*"]
        )
        self.assertEqual(issues, [])

    def test_comma_between_digits_is_not_flagged(self):
        issues = verification.compare_lines(
            ["Altura: 1,68m"], ["Altura: *"]
        )
        self.assertEqual(issues, [])

    def test_slash_between_digits_is_not_flagged(self):
        issues = verification.compare_lines(
            ["Data: 12/03/1978"], ["Data: *"]
        )
        self.assertEqual(issues, [])

    def test_web_address_is_not_flagged(self):
        url = "https://www.exemplo.pt/perfil/maria"
        issues = verification.compare_lines(
            ["Site: " + url], ["Site: *"]
        )
        self.assertEqual(issues, [])

    def test_wrong_split_is_still_flagged(self):
        issues = verification.compare_lines(
            ["Filhos: João,Ana"], ["Filhos: *"]
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "unexpected_word_change")


class CompareFilesTest(unittest.TestCase):
    def test_reads_and_compares_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_path = os.path.join(tmp, "original.txt")
            masked_path = os.path.join(tmp, "masked.txt")
            with open(original_path, "w", encoding="utf-8") as handle:
                handle.write("Nome: Maria Santos\n")
            with open(masked_path, "w", encoding="utf-8") as handle:
                handle.write("Nome: * *\n")
            issues = verification.compare_files(original_path, masked_path)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
