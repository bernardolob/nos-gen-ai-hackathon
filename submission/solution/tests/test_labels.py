"""Testes das etiquetas (``src/labels.py``)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import labels  # noqa: E402
import masking  # noqa: E402

try:
    import pipeline  # noqa: E402
except ImportError:  # o PyMuPDF não está instalado
    pipeline = None


def item(line, text, category="saude"):
    return {"line": line, "text": text, "category": category,
            "reason": "x", "confidence": "certo", "source": "gemini"}


def texts(items):
    return [i["text"] for i in items]


class ItemSpanningTheLabelTest(unittest.TestCase):
    def test_the_label_is_removed_from_an_item_that_includes_it(self):
        lines = ["Telefone: +351 912 345 678"]
        out, changes = labels.keep_labels(
            lines, [item(1, "Telefone: +351 912 345 678", "identificacao")])
        self.assertEqual(texts(out), ["+351 912 345 678"])
        self.assertEqual(changes, 1)

    def test_masking_then_keeps_the_label(self):
        lines = ["Telefone: +351 912 345 678"]
        out, _ = labels.keep_labels(
            lines, [item(1, "Telefone: +351 912 345 678")])
        masked, _ = masking.mask_lines(lines, out)
        self.assertEqual(masked, ["Telefone: * * * *"])

    def test_a_long_label_with_a_value(self):
        line = "Impressão digital registrada no sistema: ID-BIO-12345"
        out, _ = labels.keep_labels([line], [item(1, line, "biometrico")])
        self.assertEqual(texts(out), ["ID-BIO-12345"])

    def test_an_item_that_starts_inside_the_label(self):
        line = "Impressão digital registrada no sistema: ID-BIO-12345"
        out, _ = labels.keep_labels(
            [line], [item(1, "registrada no sistema: ID-BIO-12345")])
        self.assertEqual(texts(out), ["ID-BIO-12345"])

    def test_an_item_that_is_only_the_label_and_colon_is_dropped(self):
        out, _ = labels.keep_labels(["Email: a@b.pt"], [item(1, "Email:")])
        self.assertEqual(out, [])

    def test_occurrence_is_dropped_from_a_changed_item(self):
        element = dict(item(1, "Nome: Ana"), occurrence=2)
        out, _ = labels.keep_labels(["Nome: Ana"], [element])
        self.assertNotIn("occurrence", out[0])
        self.assertEqual(element["text"], "Nome: Ana")  # o original fica

    def test_the_rest_of_the_item_is_kept(self):
        element = item(1, "Nome: Ana", "identificacao")
        out, _ = labels.keep_labels(["Nome: Ana"], [element])
        self.assertEqual(out[0]["category"], "identificacao")
        self.assertEqual(out[0]["reason"], "x")
        self.assertEqual(out[0]["confidence"], "certo")
        self.assertEqual(out[0]["source"], "gemini")
        self.assertEqual(out[0]["line"], 1)


class LabelOnlyItemTest(unittest.TestCase):
    LINE = "Impressão digital registrada no sistema: ID-BIO-12345"

    def test_a_label_item_is_dropped_when_the_value_is_covered(self):
        items = [item(1, "Impressão digital", "biometrico"),
                 item(1, "ID-BIO-12345", "biometrico")]
        out, changes = labels.keep_labels([self.LINE], items)
        self.assertEqual(texts(out), ["ID-BIO-12345"])
        self.assertEqual(changes, 1)

    def test_it_is_kept_when_nobody_flagged_the_value(self):
        items = [item(1, "Impressão digital", "biometrico")]
        out, changes = labels.keep_labels([self.LINE], items)
        self.assertEqual(texts(out), ["Impressão digital"])
        self.assertEqual(changes, 0)

    def test_identification_items_in_the_label_are_never_dropped(self):
        line = "Ana Silva: diagnosticada com diabetes"
        items = [item(1, "Ana Silva", "identificacao"),
                 item(1, "diabetes", "saude")]
        out, _ = labels.keep_labels([line], items)
        self.assertEqual(texts(out), ["Ana Silva", "diabetes"])

    def test_two_label_items_and_a_value(self):
        lines = ["Reconhecimento facial: Sim"]
        items = [item(1, "Reconhecimento facial", "biometrico"),
                 item(1, "Sim", "biometrico")]
        out, _ = labels.keep_labels(lines, items)
        self.assertEqual(texts(out), ["Sim"])


class NotALabelTest(unittest.TestCase):
    def check(self, line, text):
        elements = [item(1, text)]
        out, changes = labels.keep_labels([line], elements)
        self.assertEqual(out, elements, line)
        self.assertEqual(changes, 0, line)

    def test_lines_without_a_colon(self):
        self.check("A paciente tem diabetes", "diabetes")

    def test_a_label_with_digits_or_too_many_words(self):
        self.check("Hora 10:30: consulta de HIV", "consulta de HIV")
        self.check("um dois três quatro cinco seis sete: HIV", "HIV")

    def test_a_colon_without_a_value(self):
        self.check("Alergias:", "Alergias:")

    def test_a_colon_glued_to_the_next_word(self):
        self.check("http://exemplo.pt/perfil", "http://exemplo.pt/perfil")

    def test_an_item_only_in_the_value(self):
        self.check("Nome: Ana Silva", "Ana Silva")

    def test_an_item_that_is_not_in_the_line(self):
        self.check("Nome: Ana", "Rui")

    def test_missing_or_invalid_lines_are_left_alone(self):
        elements = [item(0, "x"), item(9, "x"), {"text": "x"},
                    dict(item(1, ""), text="")]
        out, changes = labels.keep_labels(["Nome: Ana"], elements)
        self.assertEqual(out, elements)
        self.assertEqual(changes, 0)

    def test_the_input_list_is_not_modified(self):
        elements = [item(1, "Nome: Ana")]
        labels.keep_labels(["Nome: Ana"], elements)
        self.assertEqual(elements[0]["text"], "Nome: Ana")


@unittest.skipIf(pipeline is None, "o PyMuPDF não está instalado")
class PipelineTest(unittest.TestCase):
    LINES = [
        "Telefone: 912345678",
        "Impressão digital registrada no sistema: ID-BIO-12345",
        "Reconhecimento facial: Sim",
    ]

    def model(self, *elements):
        answer = json.dumps(list(elements))
        return lambda system, content: answer

    def test_the_labels_stay_visible_in_the_final_text(self):
        generate = self.model(
            item(1, "Telefone: 912345678", "identificacao"),
            item(2, "Impressão digital", "biometrico"),
            item(2, "ID-BIO-12345", "biometrico"),
            item(3, "Reconhecimento facial: Sim", "biometrico"),
        )
        result = pipeline.run(self.LINES, generate)
        self.assertEqual(result["masked"], [
            "Telefone: *",
            "Impressão digital registrada no sistema: *",
            "Reconhecimento facial: *",
        ])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["label_changes"], 3)
        self.assertIn("etiquetas deixadas visíveis: 3",
                      pipeline.summary(result))

    def test_no_message_without_changes(self):
        result = pipeline.run(["Nome: Ana"], self.model())
        self.assertNotIn("etiquetas", pipeline.summary(result))


if __name__ == "__main__":
    unittest.main()
