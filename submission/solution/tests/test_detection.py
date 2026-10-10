"""Testes da deteção (``src/detection.py``)."""

import json
import sys
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import detection  # noqa: E402
import masking  # noqa: E402
import report  # noqa: E402

LINES = [
    "Nome: Rui Pinto",
    "NIF: 123456789",
    "Salário mensal: 2.350 EUR",
]

NAME = {
    "line": 1,
    "text": "Rui Pinto",
    "category": "identificacao",
    "reason": "Nome do funcionário.",
    "confidence": "certo",
}
NIF = {
    "line": 2,
    "text": "123456789",
    "category": "identificacao",
    "reason": "NIF.",
    "confidence": "certo",
}
SALARY = {
    "line": 3,
    "text": "2.350 EUR",
    "category": "financeiro",
    "reason": "Remuneração.",
    "confidence": "provavel",
}


def answer(*elements):
    """Resposta do modelo: uma lista JSON."""
    return json.dumps(list(elements), ensure_ascii=False)


class FakeModel:
    """Cliente falso: devolve as respostas por ordem e regista os pedidos."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, system_prompt, request):
        self.calls.append((system_prompt, request))
        return self.answers.pop(0)


class BuildRequestTest(unittest.TestCase):
    def test_number_lines_starts_at_one(self):
        self.assertEqual(
            detection.number_lines(["a", "b"]),
            "[1] a\n[2] b",
        )

    def test_request_wraps_the_numbered_document(self):
        request = detection.build_request(LINES)
        self.assertEqual(
            request,
            "<document>\n"
            "[1] Nome: Rui Pinto\n"
            "[2] NIF: 123456789\n"
            "[3] Salário mensal: 2.350 EUR\n"
            "</document>",
        )

    def test_user_instructions_go_in_their_own_block(self):
        request = detection.build_request(LINES, "  Mascara as datas.  ")
        self.assertTrue(request.endswith(
            "</document>\n\n"
            "<user_instructions>\nMascara as datas.\n</user_instructions>"
        ))

    def test_blank_user_instructions_are_ignored(self):
        for blank in (None, "", "   \n"):
            request = detection.build_request(LINES, blank)
            self.assertNotIn("user_instructions", request)

    def test_internal_prompt_is_loaded(self):
        prompt = detection.load_internal_prompt()
        self.assertIn("<document>", prompt)
        self.assertIn("<user_instructions>", prompt)
        for category in detection.CATEGORY_NAMES:
            self.assertIn(category, prompt)

    def test_normalize_lines_to_nfc(self):
        decomposed = unicodedata.normalize("NFD", "Conceição")
        self.assertNotEqual(decomposed, "Conceição")
        self.assertEqual(detection.normalize_lines([decomposed]),
                         ["Conceição"])


class ParseResponseTest(unittest.TestCase):
    def test_valid_items(self):
        items, warnings = detection.parse_response(
            answer(NAME, NIF, SALARY), LINES)
        self.assertEqual(warnings, [])
        self.assertEqual([i["text"] for i in items],
                         ["Rui Pinto", "123456789", "2.350 EUR"])
        self.assertTrue(all(i["source"] == "gemini" for i in items))
        self.assertEqual(items[2]["category"], "financeiro")
        self.assertEqual(items[2]["confidence"], "provavel")

    def test_empty_list(self):
        self.assertEqual(detection.parse_response("[]", LINES), ([], []))

    def test_code_fence_is_tolerated(self):
        fenced = "```json\n" + answer(NAME) + "\n```"
        items, _ = detection.parse_response(fenced, LINES)
        self.assertEqual(len(items), 1)

    def test_text_around_the_list_is_tolerated(self):
        wrapped = "Aqui está:\n" + answer(NAME) + "\nEspero que ajude."
        items, _ = detection.parse_response(wrapped, LINES)
        self.assertEqual(len(items), 1)

    def test_text_is_normalized_to_nfc(self):
        item = dict(NAME, text=unicodedata.normalize("NFD", "Conceição"))
        items, _ = detection.parse_response(answer(item), LINES)
        self.assertEqual(items[0]["text"], "Conceição")

    def test_occurrence_is_kept(self):
        items, _ = detection.parse_response(
            answer(dict(NAME, occurrence=2)), LINES)
        self.assertEqual(items[0]["occurrence"], 2)

    def test_reason_is_optional(self):
        item = {k: v for k, v in NAME.items() if k != "reason"}
        items, warnings = detection.parse_response(answer(item), LINES)
        self.assertEqual(items[0]["reason"], "")
        self.assertEqual(warnings, [])

    def test_duplicates_count_once(self):
        items, warnings = detection.parse_response(
            answer(NAME, NAME), LINES)
        self.assertEqual(len(items), 1)
        self.assertEqual(warnings, [])

    def test_same_text_on_another_line_is_not_a_duplicate(self):
        items, _ = detection.parse_response(
            answer(NAME, dict(NAME, line=3)), LINES)
        self.assertEqual(len(items), 2)

    def test_not_json_raises(self):
        for bad in ("não é json", "", "   ", None, 42):
            with self.assertRaises(detection.DetectionError, msg=repr(bad)):
                detection.parse_response(bad, LINES)

    def test_json_that_is_not_a_list_raises(self):
        with self.assertRaises(detection.DetectionError):
            detection.parse_response(json.dumps(NAME), LINES)


class InvalidItemsTest(unittest.TestCase):
    def check(self, element, problem):
        items, warnings = detection.parse_response(
            answer(NAME, element), LINES)
        self.assertEqual([i["text"] for i in items], ["Rui Pinto"])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["index"], 1)
        self.assertIn(problem, warnings[0]["problem"])

    def test_line_out_of_range(self):
        self.check(dict(NAME, line=0), "linha")
        self.check(dict(NAME, line=4), "linha")
        self.check(dict(NAME, line="1"), "linha")
        self.check(dict(NAME, line=True), "linha")
        self.check({k: v for k, v in NAME.items() if k != "line"}, "linha")

    def test_text_missing_or_empty(self):
        self.check(dict(NAME, text=""), "texto")
        self.check(dict(NAME, text="   "), "texto")
        self.check(dict(NAME, text=5), "texto")

    def test_unknown_category(self):
        self.check(dict(NAME, category="outra"), "categoria")
        self.check({k: v for k, v in NAME.items() if k != "category"},
                   "categoria")

    def test_unknown_confidence(self):
        self.check(dict(NAME, confidence="talvez"), "confiança")

    def test_bad_reason(self):
        self.check(dict(NAME, reason=7), "razão")

    def test_bad_occurrence(self):
        self.check(dict(NAME, occurrence=0), "ocorrência")
        self.check(dict(NAME, occurrence="2"), "ocorrência")
        self.check(dict(NAME, occurrence=True), "ocorrência")

    def test_element_that_is_not_an_object(self):
        self.check("Rui Pinto", "objeto")
        self.check(None, "objeto")

    def test_warning_carries_line_and_text_but_problem_does_not(self):
        _, warnings = detection.parse_response(
            answer(dict(NAME, category="outra")), LINES)
        self.assertEqual(warnings[0]["line"], 1)
        self.assertEqual(warnings[0]["text"], "Rui Pinto")
        self.assertNotIn("Rui Pinto", warnings[0]["problem"])


class DetectTest(unittest.TestCase):
    def test_sends_prompt_and_numbered_document(self):
        model = FakeModel(answer(NAME))
        detection.detect(LINES, model)
        system_prompt, request = model.calls[0]
        self.assertEqual(system_prompt, detection.load_internal_prompt())
        self.assertEqual(request, detection.build_request(LINES))

    def test_custom_prompt_and_user_instructions(self):
        model = FakeModel(answer())
        detection.detect(LINES, model, user_instructions="Extra.",
                         system_prompt="PROMPT")
        system_prompt, request = model.calls[0]
        self.assertEqual(system_prompt, "PROMPT")
        self.assertIn("<user_instructions>\nExtra.", request)

    def test_returns_items_and_warnings(self):
        model = FakeModel(answer(NAME, dict(NIF, category="x")))
        items, warnings = detection.detect(LINES, model)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(warnings), 1)

    def test_retries_once_on_unusable_answer(self):
        model = FakeModel("lixo", answer(NAME))
        items, _ = detection.detect(LINES, model)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(len(items), 1)

    def test_fails_after_all_attempts(self):
        model = FakeModel("lixo", "mais lixo")
        with self.assertRaises(detection.DetectionError) as caught:
            detection.detect(LINES, model)
        self.assertEqual(len(model.calls), 2)
        self.assertIn("2 tentativa", str(caught.exception))

    def test_attempts_can_be_set(self):
        model = FakeModel("a", "b", "c")
        with self.assertRaises(detection.DetectionError):
            detection.detect(LINES, model, attempts=3)
        self.assertEqual(len(model.calls), 3)

    def test_at_least_one_attempt(self):
        model = FakeModel("a")
        with self.assertRaises(detection.DetectionError):
            detection.detect(LINES, model, attempts=0)
        self.assertEqual(len(model.calls), 1)

    def test_invalid_items_do_not_trigger_a_retry(self):
        model = FakeModel(answer(dict(NAME, category="x")))
        items, warnings = detection.detect(LINES, model)
        self.assertEqual((items, len(warnings)), ([], 1))
        self.assertEqual(len(model.calls), 1)

    def test_blank_document_does_not_call_the_model(self):
        model = FakeModel()
        self.assertEqual(detection.detect([], model), ([], []))
        self.assertEqual(detection.detect(["", "  "], model), ([], []))
        self.assertEqual(model.calls, [])

    def test_errors_from_the_model_client_propagate(self):
        def broken(_system_prompt, _request):
            raise RuntimeError("client down")

        with self.assertRaises(RuntimeError):
            detection.detect(LINES, broken)

    def test_error_messages_never_repeat_the_answer(self):
        secret = "Rui Pinto 123456789"
        model = FakeModel(secret, secret)
        with self.assertRaises(detection.DetectionError) as caught:
            detection.detect(LINES, model)
        self.assertNotIn("Rui", str(caught.exception))
        self.assertNotIn("123456789", str(caught.exception))


class EndToEndTest(unittest.TestCase):
    """A deteção, o mascaramento e o relatório com o mesmo contrato."""

    def test_detected_items_feed_masking_and_report(self):
        model = FakeModel(answer(NAME, NIF, SALARY))
        items, warnings = detection.detect(LINES, model)
        masked, mask_warnings = masking.mask_lines(LINES, items)
        self.assertEqual(masked, [
            "Nome: * *",
            "NIF: *",
            "Salário mensal: * *",
        ])
        self.assertEqual(mask_warnings, [])
        text = report.build_report(items, warnings + mask_warnings)
        self.assertIn("- Itens ocultados: 3", text)
        self.assertIn("Gemini", text)
        self.assertNotIn("Rui Pinto", text)


if __name__ == "__main__":
    unittest.main()
