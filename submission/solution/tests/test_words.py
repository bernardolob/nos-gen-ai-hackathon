"""Testes das palavras (``src/words.py``).

A regra de "o que é uma palavra" é partilhada pelo mascaramento e pela
verificação, por isso tem testes próprios.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import masking  # noqa: E402
import verification  # noqa: E402
import words  # noqa: E402


class MaskWordTest(unittest.TestCase):
    def test_a_word_becomes_one_asterisk(self):
        self.assertEqual(words.mask_word("Maria"), "*")

    def test_punctuation_at_the_edges_is_kept(self):
        self.assertEqual(words.mask_word("Santos,"), "*,")
        self.assertEqual(words.mask_word("(João,"), "(*,")
        self.assertEqual(words.mask_word("Mendes."), "*.")

    def test_symbols_are_part_of_the_word(self):
        self.assertEqual(words.mask_word("+351"), "*")
        self.assertEqual(words.mask_word("€62.500"), "*")

    def test_a_lone_symbol_is_not_a_word(self):
        for symbol in ("-", "—", "€", "+", ""):
            self.assertEqual(words.mask_word(symbol), symbol)


class MaskTokenTest(unittest.TestCase):
    def test_comma_semicolon_and_slash_separate_words(self):
        self.assertEqual(words.mask_token("João,Ana"), "*,*")
        self.assertEqual(words.mask_token("Rui;Ana;Rita"), "*;*;*")
        self.assertEqual(words.mask_token("Rui/Ana"), "*/*")

    def test_between_digits_they_do_not_separate(self):
        for token in ("1,68m", "2.350,50", "12/03/1978", "145/90"):
            self.assertEqual(words.mask_token(token), "*", token)

    def test_hyphen_does_not_separate(self):
        self.assertEqual(words.mask_token("Ana-Maria"), "*")

    def test_web_addresses_are_one_word(self):
        self.assertEqual(
            words.mask_token("https://www.x.pt/perfil/ana."), "*.")

    def test_edge_punctuation_with_separators(self):
        self.assertEqual(words.mask_token("(João,Ana)"), "(*,*)")


class WrittenDateTest(unittest.TestCase):
    """Datas com o mês escrito são uma só palavra, apesar das barras."""

    def test_day_month_year(self):
        for token in ("12/mar/1978", "12/Mar/1978", "3/março/1978",
                      "01/dezembro/99", "12/Jan/2025", "12/sept/2025"):
            self.assertEqual(words.mask_token(token), "*", token)

    def test_month_and_year_only(self):
        self.assertEqual(words.mask_token("mar/1978"), "*")
        self.assertEqual(words.mask_token("Março/2025"), "*")

    def test_day_and_month_only(self):
        self.assertEqual(words.mask_token("12/mar"), "*")

    def test_punctuation_around_the_date_is_kept(self):
        self.assertEqual(words.mask_token("(12/mar/1978),"), "(*),")

    def test_only_real_months_count(self):
        """Uma palavra qualquer entre barras continua a separar."""
        self.assertEqual(words.mask_token("12/xyz/1978"), "*/*/*")
        self.assertEqual(words.mask_token("Rui/2"), "*/*")
        self.assertEqual(words.mask_token("ana/1978"), "*/*")

    def test_a_month_next_to_another_word_is_not_a_date(self):
        self.assertEqual(words.mask_token("Rui/mar"), "*/*")


class WholeWordPatternTest(unittest.TestCase):
    def starts(self, text, line):
        pattern = words.whole_word_pattern(text)
        return [m.start() for m in pattern.finditer(line)]

    def test_finds_whole_words_only(self):
        self.assertEqual(self.starts("Ana", "Ana e Ana"), [0, 6])
        self.assertEqual(self.starts("Ana", "Anabela e Ana"), [10])
        self.assertEqual(self.starts("ana", "Mariana e ana"), [10])

    def test_punctuation_is_a_boundary(self):
        self.assertEqual(self.starts("Ana", "(Ana), Ana; Ana."), [1, 7, 12])

    def test_a_hyphen_between_word_characters_joins_words(self):
        for line in ("Ana-Maria", "Maria-Ana", "Ana-1", "x-Ana-y"):
            self.assertEqual(self.starts("Ana", line), [], line)

    def test_unicode_hyphens_join_words_too(self):
        self.assertEqual(self.starts("Ana", "Ana‑Maria"), [])
        self.assertEqual(self.starts("Ana", "Ana‐Maria"), [])

    def test_a_hyphen_that_does_not_join_two_words(self):
        for line in ("Ana - Maria", "- Ana", " -Ana", "Ana-", "Ana – Maria"):
            self.assertEqual(len(self.starts("Ana", line)), 1, line)

    def test_special_characters_in_the_text_are_literal(self):
        self.assertEqual(self.starts("(a+b)?", "x (a+b)? y"), [2])

    def test_multi_word_text(self):
        self.assertEqual(
            self.starts("Rui Pinto", "Rui Pintor e Rui Pinto"), [13])


class SharedRuleTest(unittest.TestCase):
    """O mascaramento e a verificação usam a mesma regra, não uma cópia."""

    def test_masking_and_verification_use_the_shared_functions(self):
        self.assertIs(masking.mask_token, words.mask_token)
        self.assertIs(verification.mask_token, words.mask_token)

    CASES = [
        "João,Ana", "Rui/Ana", "1,68m", "12/03/1978", "12/mar/1978",
        "Ana-Maria", "(João,", "https://www.x.pt/a.", "+351", "-", "mar/2025",
    ]

    def test_what_masking_produces_always_passes_the_verification(self):
        for token in self.CASES:
            line = "Campo: %s fim" % token
            out, _ = masking.mask_lines(
                [line], [{"line": 1, "text": token}])
            self.assertEqual(
                verification.compare_lines([line], out), [], token)


if __name__ == "__main__":
    unittest.main()
