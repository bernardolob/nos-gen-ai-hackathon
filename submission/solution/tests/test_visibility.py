"""Testes dos valores deixados visíveis (``src/visibility.py``)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import detection  # noqa: E402
import visibility  # noqa: E402

try:
    import pipeline  # noqa: E402
except ImportError:  # o PyMuPDF não está instalado
    pipeline = None

LINES = ["Email: ana@x.pt", "NIF: 123456789", "Contacto: ana@x.pt e rui@y.pt"]


def item(line, text, **extra):
    base = {"line": line, "text": text, "category": "identificacao",
            "reason": "x", "confidence": "certo"}
    base.update(extra)
    return base


class SplitTest(unittest.TestCase):
    def test_visible_items_are_separated(self):
        masks, visible = visibility.split_visible(
            [item(1, "a"), item(2, "b", visible=True), item(3, "c")])
        self.assertEqual([i["text"] for i in masks], ["a", "c"])
        self.assertEqual([i["text"] for i in visible], ["b"])


class DropOverlappingTest(unittest.TestCase):
    def drop(self, items, visible):
        return visibility.drop_overlapping(LINES, items, visible)

    def test_an_item_on_a_visible_value_is_dropped(self):
        kept, dropped = self.drop(
            [item(1, "ana@x.pt"), item(2, "123456789")],
            [item(1, "ana@x.pt")])
        self.assertEqual([i["text"] for i in kept], ["123456789"])
        self.assertEqual(dropped, 1)

    def test_overlap_by_position_even_with_different_sizes(self):
        kept, _ = self.drop([item(1, "Email: ana@x.pt")],
                            [item(1, "ana@x.pt")])
        self.assertEqual(kept, [])
        kept, _ = self.drop([item(1, "x.pt")], [item(1, "ana@x.pt")])
        self.assertEqual(kept, [])

    def test_the_same_text_on_another_line_is_not_affected(self):
        kept, dropped = self.drop([item(3, "ana@x.pt")],
                                  [item(1, "ana@x.pt")])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)

    def test_every_occurrence_in_the_line_counts(self):
        kept, _ = self.drop([item(3, "ana@x.pt"), item(3, "rui@y.pt")],
                            [item(3, "ana@x.pt")])
        self.assertEqual([i["text"] for i in kept], ["rui@y.pt"])

    def test_touching_is_not_overlapping(self):
        kept, _ = self.drop([item(2, "NIF:")], [item(2, "123456789")])
        self.assertEqual(len(kept), 1)

    def test_invalid_items_are_left_alone(self):
        weird = [item(0, "x"), item(9, "x"), {"text": "x"}, item(1, "zzz"),
                 dict(item(1, ""), text="")]
        kept, dropped = self.drop(weird, [item(1, "ana@x.pt"), item(7, "q")])
        self.assertEqual(kept, weird)
        self.assertEqual(dropped, 0)


class ParseTest(unittest.TestCase):
    def parse(self, **extra):
        answer = json.dumps([item(1, "ana@x.pt", **extra)])
        return detection.parse_response(answer, LINES)[0][0]

    def test_visible_true_is_kept(self):
        self.assertIs(self.parse(visible=True)["visible"], True)

    def test_anything_else_is_ignored(self):
        for value in (False, "true", 1, None):
            self.assertNotIn("visible", self.parse(visible=value))

    def test_it_survives_the_line_split(self):
        doc = ["um dois", "três quatro"]
        answer = json.dumps([item(1, "dois\n[2] três", visible=True)])
        items, _ = detection.parse_response(answer, doc)
        self.assertEqual([i["line"] for i in items], [1, 2])
        self.assertTrue(all(i["visible"] for i in items))


@unittest.skipIf(pipeline is None, "o PyMuPDF não está instalado")
class PipelineTest(unittest.TestCase):
    def model(self, *elements):
        answer = json.dumps(list(elements))
        return lambda system, content: answer

    def run_it(self, instructions, *elements):
        return pipeline.run(
            LINES[:2], self.model(*elements), instructions)

    def test_regex_rules_obey_the_user(self):
        result = self.run_it(
            "Não mascares os emails.",
            item(1, "ana@x.pt", visible=True))
        self.assertEqual(result["masked"], ["Email: ana@x.pt", "NIF: *"])
        self.assertEqual(result["kept_visible"], 1)
        self.assertEqual(result["issues"], [])
        self.assertIn("deixados visíveis a pedido do utilizador: 1",
                      pipeline.summary(result))

    def test_a_visible_value_wins_over_a_masked_item(self):
        result = self.run_it(
            "Não mascares os emails.",
            item(1, "ana@x.pt"), item(1, "ana@x.pt", visible=True))
        self.assertEqual(result["masked"][0], "Email: ana@x.pt")

    def test_without_user_instructions_it_is_ignored(self):
        result = self.run_it(None, item(1, "ana@x.pt", visible=True))
        self.assertEqual(result["masked"], ["Email: *", "NIF: *"])
        self.assertEqual(result["kept_visible"], 0)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("sem instruções", result["warnings"][0]["problem"])

    def test_the_report_does_not_list_visible_values(self):
        result = self.run_it(
            "Não mascares os emails.",
            item(1, "ana@x.pt", visible=True))
        self.assertNotIn("ana@x.pt", result["report"])

    def test_nothing_changes_when_nothing_is_visible(self):
        result = self.run_it("Mascara tudo.")
        self.assertEqual(result["kept_visible"], 0)
        self.assertNotIn("visíveis", pipeline.summary(result))


if __name__ == "__main__":
    unittest.main()
