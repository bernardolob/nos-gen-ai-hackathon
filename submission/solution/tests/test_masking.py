"""Testes do mascaramento (``src/masking.py``)."""

import sys
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import masking  # noqa: E402
import verification  # noqa: E402


def mask(lines, items):
    """Atalho: devolve as linhas mascaradas e os avisos."""
    return masking.mask_lines(lines, items)


class MaskWordsTest(unittest.TestCase):
    def test_one_asterisk_per_word(self):
        out, warnings = mask(
            ["Nome: Maria Conceição Oliveira Santos"],
            [{"line": 1, "text": "Maria Conceição Oliveira Santos"}],
        )
        self.assertEqual(out, ["Nome: * * * *"])
        self.assertEqual(warnings, [])

    def test_phone_number_words(self):
        out, _ = mask(
            ["Telefone: +351 912 345 678"],
            [{"line": 1, "text": "+351 912 345 678"}],
        )
        self.assertEqual(out, ["Telefone: * * * *"])

    def test_punctuation_at_word_edges_is_kept(self):
        out, _ = mask(
            ["Filhos: 2 (João, 15 anos e Ana, 12 anos)"],
            [
                {"line": 1, "text": "2"},
                {"line": 1, "text": "João, 15 anos"},
                {"line": 1, "text": "Ana, 12 anos"},
            ],
        )
        self.assertEqual(out, ["Filhos: * (*, * * e *, * *)"])

    def test_address_keeps_commas(self):
        out, _ = mask(
            ["Morada: Rua das Flores, 123, Apt 45, Sacavém, Lisboa"],
            [{
                "line": 1,
                "text": "Rua das Flores, 123, Apt 45, Sacavém, Lisboa",
            }],
        )
        self.assertEqual(out, ["Morada: * * *, *, * *, *, *"])

    def test_isolated_symbol_is_not_a_word(self):
        out, _ = mask(
            ["Admissão - Centro Médico"],
            [{"line": 1, "text": "Admissão - Centro"}],
        )
        self.assertEqual(out, ["* - * Médico"])

    def test_spaces_are_preserved(self):
        out, _ = mask(
            ["Nome:  Maria   Santos"],
            [{"line": 1, "text": "Maria   Santos"}],
        )
        self.assertEqual(out, ["Nome:  *   *"])

    def test_regex_characters_in_text(self):
        out, _ = mask(
            ["Valor (a+b)? [x]"],
            [{"line": 1, "text": "(a+b)?"}],
        )
        self.assertEqual(out, ["Valor (*)? [x]"])

    def test_no_items_changes_nothing(self):
        out, warnings = mask(["texto igual"], [])
        self.assertEqual(out, ["texto igual"])
        self.assertEqual(warnings, [])

    def test_line_count_is_preserved(self):
        lines = ["a", "Maria Santos", "c"]
        out, _ = mask(lines, [{"line": 2, "text": "Maria Santos"}])
        self.assertEqual(len(out), len(lines))


class JoinedWordsTest(unittest.TestCase):
    def test_comma_without_space_separates_words(self):
        out, _ = mask(["Filhos: João,Ana"], [{"line": 1, "text": "João,Ana"}])
        self.assertEqual(out, ["Filhos: *,*"])

    def test_comma_with_and_without_space_agree(self):
        joined, _ = mask(["João,Ana"], [{"line": 1, "text": "João,Ana"}])
        spaced, _ = mask(["João, Ana"], [{"line": 1, "text": "João, Ana"}])
        self.assertEqual(joined[0].count("*"), spaced[0].count("*"))

    def test_semicolon_separates_words(self):
        out, _ = mask(
            ["Contactos: Rui;Ana;Rita"],
            [{"line": 1, "text": "Rui;Ana;Rita"}],
        )
        self.assertEqual(out, ["Contactos: *;*;*"])

    def test_surname_first_format(self):
        out, _ = mask(
            ["Nome: Santos,Maria"],
            [{"line": 1, "text": "Santos,Maria"}],
        )
        self.assertEqual(out, ["Nome: *,*"])

    def test_surrounding_punctuation_is_kept(self):
        out, _ = mask(["Filhos:(João,Ana)"], [{"line": 1, "text": "João,Ana"}])
        self.assertEqual(out, ["Filhos:(*,*)"])

    def test_comma_between_letter_and_digit_separates(self):
        out, _ = mask(
            ["Rua das Flores,123"],
            [{"line": 1, "text": "Rua das Flores,123"}],
        )
        self.assertEqual(out, ["* * *,*"])

    def test_comma_between_digits_does_not_separate(self):
        for line, text in (
            ("Altura: 1,68m", "1,68m"),
            ("Salário: 2.350,50", "2.350,50"),
            ("Dose: 0,5mg", "0,5mg"),
        ):
            out, _ = mask([line], [{"line": 1, "text": text}])
            self.assertEqual(out, [line.replace(text, "*")], line)

    def test_slash_between_words_separates(self):
        out, _ = mask(
            ["Pessoas: Rui/Ana"],
            [{"line": 1, "text": "Rui/Ana"}],
        )
        self.assertEqual(out, ["Pessoas: */*"])
        out, _ = mask(["Pessoas: a/b/c"], [{"line": 1, "text": "a/b/c"}])
        self.assertEqual(out, ["Pessoas: */*/*"])

    def test_slash_between_digits_does_not_separate(self):
        for line, text in (
            ("Data: 12/03/1978", "12/03/1978"),
            ("Pressão: 145/90", "145/90"),
            ("Validade: 09/27", "09/27"),
        ):
            out, _ = mask([line], [{"line": 1, "text": text}])
            self.assertEqual(out, [line.replace(text, "*")], line)

    def test_slash_between_letter_and_digit_separates(self):
        out, _ = mask(
            ["Data: 12/mar/1978"],
            [{"line": 1, "text": "12/mar/1978"}],
        )
        self.assertEqual(out, ["Data: */*/*"])

    def test_hyphen_does_not_separate(self):
        out, _ = mask(
            ["Nome: Ana-Maria"],
            [{"line": 1, "text": "Ana-Maria"}],
        )
        self.assertEqual(out, ["Nome: *"])

    def test_web_address_is_a_single_word(self):
        url = "https://www.exemplo.pt/perfil/maria"
        out, _ = mask(["Site: " + url], [{"line": 1, "text": url}])
        self.assertEqual(out, ["Site: *"])
        out, _ = mask(
            ["Ver www.exemplo.pt/maria."],
            [{"line": 1, "text": "www.exemplo.pt/maria"}],
        )
        self.assertEqual(out, ["Ver *."])

    def test_email_is_a_single_word(self):
        out, _ = mask(
            ["Email: ana.silva@x.pt"],
            [{"line": 1, "text": "ana.silva@x.pt"}],
        )
        self.assertEqual(out, ["Email: *"])


class LocateItemsTest(unittest.TestCase):
    def test_wrong_line_falls_back_to_neighbour(self):
        out, warnings = mask(
            ["a", "Joana Pereira", "c"],
            [{"line": 1, "text": "Joana Pereira"}],
        )
        self.assertEqual(out, ["a", "* *", "c"])
        self.assertEqual(warnings, [])

    def test_missing_or_out_of_range_line(self):
        out, warnings = mask(
            ["Carlos Mendes"],
            [{"line": 50, "text": "Carlos Mendes"}, {"text": "Mendes"}],
        )
        self.assertEqual(out, ["* *"])
        self.assertEqual(warnings, [])

    def test_item_not_found_gives_warning(self):
        out, warnings = mask(
            ["Nome: Maria"],
            [{"line": 1, "text": "texto inexistente"}],
        )
        self.assertEqual(out, ["Nome: Maria"])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["text"], "texto inexistente")

    def test_empty_text_gives_warning(self):
        out, warnings = mask(["abc"], [{"line": 1, "text": "  "}])
        self.assertEqual(out, ["abc"])
        self.assertEqual(len(warnings), 1)

    def test_decomposed_accent_is_not_found(self):
        line = unicodedata.normalize("NFC", "Conceição")
        text = unicodedata.normalize("NFD", "Conceição")
        out, warnings = mask([line], [{"line": 1, "text": text}])
        self.assertEqual(out, [line])
        self.assertEqual(len(warnings), 1)

    def test_overlapping_items_are_merged(self):
        out, _ = mask(
            ["Maria Conceição Santos"],
            [
                {"line": 1, "text": "Maria Conceição"},
                {"line": 1, "text": "Conceição Santos"},
            ],
        )
        self.assertEqual(out, ["* * *"])

    def test_occurrence_for_short_numbers(self):
        out, _ = mask(
            ["Sala 7 e andar 7"],
            [{"line": 1, "text": "7", "occurrence": 2}],
        )
        self.assertEqual(out, ["Sala 7 e andar *"])

    def test_occurrence_beyond_count_uses_first(self):
        out, _ = mask(
            ["Sala 7"],
            [{"line": 1, "text": "7", "occurrence": 3}],
        )
        self.assertEqual(out, ["Sala *"])


class WholeWordTest(unittest.TestCase):
    """O valor é a palavra inteira, não o início ou o fim de outra."""

    def test_prefix_of_a_longer_word_is_not_masked(self):
        out, warnings = mask(
            ["Anabela e Ana"],
            [{"line": 1, "text": "Ana"}],
        )
        self.assertEqual(out, ["Anabela e *"])
        self.assertEqual(warnings, [])

    def test_suffix_of_a_longer_word_is_not_masked(self):
        out, _ = mask(
            ["Mariana e Ana"],
            [{"line": 1, "text": "Ana"}],
        )
        self.assertEqual(out, ["Mariana e *"])

    def test_multi_word_value_inside_a_longer_one(self):
        out, _ = mask(
            ["Rui Pintor e Rui Pinto"],
            [{"line": 1, "text": "Rui Pinto"}],
        )
        self.assertEqual(out, ["Rui Pintor e * *"])

    def test_the_first_whole_word_wins_when_there_are_several(self):
        out, _ = mask(
            ["Ana viu Anabela e Ana"],
            [{"line": 1, "text": "Ana", "occurrence": 1}],
        )
        self.assertEqual(out, ["* viu Anabela e *"])

    def test_occurrence_counts_whole_words_only(self):
        out, _ = mask(
            ["7 e 70 e 7"],
            [{"line": 1, "text": "7", "occurrence": 2}],
        )
        self.assertEqual(out, ["7 e 70 e *"])

    def test_whole_word_on_a_neighbour_beats_a_part_of_a_word(self):
        out, warnings = mask(
            ["Anabela", "Ana"],
            [{"line": 1, "text": "Ana"}],
        )
        self.assertEqual(out, ["Anabela", "*"])
        self.assertEqual(warnings, [])

    def test_whole_word_in_the_stated_line_beats_one_next_door(self):
        out, _ = mask(
            ["Ana", "Ana e Rui", "Ana"],
            [{"line": 2, "text": "Rui"}],
        )
        self.assertEqual(out, ["Ana", "Ana e *", "Ana"])

    def test_without_a_whole_word_the_part_of_a_word_is_still_masked(self):
        """Protege o valor, mesmo que o resto da palavra fique visível."""
        out, warnings = mask(["ID12345"], [{"line": 1, "text": "12345"}])
        self.assertEqual(out, ["ID*"])
        self.assertEqual(warnings, [])

    def test_text_with_symbols_at_the_edges(self):
        out, _ = mask(
            ["Tel: +351 912 345 678 e x+351"],
            [{"line": 1, "text": "+351 912 345 678"}],
        )
        self.assertEqual(out, ["Tel: * * * * e x+351"])

    def test_punctuation_around_the_word_still_counts_as_a_boundary(self):
        out, _ = mask(
            ["(Ana), Anabela; Ana."],
            [{"line": 1, "text": "Ana"}],
        )
        self.assertEqual(out, ["(*), Anabela; *."])

    def test_occurrence_beyond_the_count_uses_the_first(self):
        out, _ = mask(
            ["Anabela e Ana"],
            [{"line": 1, "text": "Ana", "occurrence": 5}],
        )
        self.assertEqual(out, ["Anabela e *"])

    def test_the_output_passes_the_verification(self):
        cases = [
            (["Anabela e Ana"], "Ana"),
            (["Mariana e Ana"], "Ana"),
            (["Rui Pintor e Rui Pinto"], "Rui Pinto"),
            (["(Ana), Anabela; Ana."], "Ana"),
            (["7 e 70 e 7"], "7"),
        ]
        for lines, text in cases:
            out, _ = mask(lines, [{"line": 1, "text": text}])
            self.assertEqual(
                verification.compare_lines(lines, out), [], lines)


class PropagationTest(unittest.TestCase):
    def test_other_occurrences_are_masked(self):
        out, _ = mask(
            ["Nome: Maria Santos", "A paciente Maria Santos chegou."],
            [{"line": 1, "text": "Maria Santos"}],
        )
        self.assertEqual(out, ["Nome: * *", "A paciente * * chegou."])

    def test_short_name_with_letters_propagates(self):
        out, _ = mask(
            ["Ana e Anabela", "Anabela foi com a Ana."],
            [{"line": 1, "text": "Ana"}],
        )
        self.assertEqual(out, ["* e Anabela", "Anabela foi com a *."])

    def test_whole_word_only(self):
        out, _ = mask(
            ["Ana", "Banana e Anabela"],
            [{"line": 1, "text": "Ana"}],
        )
        self.assertEqual(out, ["*", "Banana e Anabela"])

    def test_short_numbers_do_not_propagate(self):
        out, _ = mask(
            ["Filhos: 2", "Rua 2, 2 andar"],
            [{"line": 1, "text": "2"}],
        )
        self.assertEqual(out, ["Filhos: *", "Rua 2, 2 andar"])

    def test_long_numbers_propagate(self):
        out, _ = mask(
            ["Desde 2018", "Em 2018 houve consulta"],
            [{"line": 1, "text": "2018"}],
        )
        self.assertEqual(out, ["Desde *", "Em * houve consulta"])


if __name__ == "__main__":
    unittest.main()
