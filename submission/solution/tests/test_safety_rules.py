"""Testes das regras de segurança (``src/safety_rules.py``)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import safety_rules  # noqa: E402


def found_texts(lines):
    """Devolve só os textos encontrados, por ordem."""
    return [item["text"] for item in safety_rules.find_sensitive(lines)]


class SafetyRulesTest(unittest.TestCase):
    def test_email(self):
        self.assertEqual(
            found_texts(["Email: maria.santos@emailpessoal.pt"]),
            ["maria.santos@emailpessoal.pt"],
        )

    def test_phone_with_and_without_spaces(self):
        self.assertEqual(
            found_texts(["Telefone: +351 912 345 678"]),
            ["+351 912 345 678"],
        )
        self.assertEqual(
            found_texts(["Telefone: +351961234567"]),
            ["+351961234567"],
        )

    def test_labelled_identifiers_return_only_the_value(self):
        self.assertEqual(found_texts(["NIF: 097865413"]), ["097865413"])
        self.assertEqual(
            found_texts(["Cartão de Cidadão: 12345678-9ZX0"]),
            ["12345678-9ZX0"],
        )
        self.assertEqual(
            found_texts(["Número da Segurança Social: 11223344556"]),
            ["11223344556"],
        )
        self.assertEqual(found_texts(["CRM: 12345-PT"]), ["12345-PT"])
        self.assertEqual(
            found_texts(["Data de Nascimento: 12/03/1978"]),
            ["12/03/1978"],
        )

    def test_unlabelled_number_is_not_flagged(self):
        self.assertEqual(found_texts(["Código 097865413"]), [])

    def test_card_expiry_and_cvv(self):
        line = "Cartão: 4111 2222 3333 4444 (validade 09/27, CVV 123)"
        self.assertEqual(
            found_texts([line]),
            ["4111 2222 3333 4444", "09/27", "123"],
        )

    def test_policy_number(self):
        self.assertEqual(
            found_texts(["Plano Premium, apólice nº 987654321"]),
            ["987654321"],
        )

    def test_biometric_ids(self):
        self.assertEqual(
            found_texts([
                "Impressão digital registada: ID-BIO-12345",
                "Reconhecimento facial: FACE-ID-78901",
            ]),
            ["ID-BIO-12345", "FACE-ID-78901"],
        )

    def test_reference_and_dates_are_not_flagged(self):
        lines = [
            "Data: 15 de abril de 2025",
            "Referência: ADM-2025-04-15-089",
            "Rendimento anual declarado: €62.500",
        ]
        self.assertEqual(found_texts(lines), [])

    def test_item_fields(self):
        items = safety_rules.find_sensitive(["a", "NIF: 097865413"])
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["line"], 2)
        self.assertEqual(item["category"], "identificacao")
        self.assertEqual(item["confidence"], "certo")
        self.assertEqual(item["source"], "regex")
        self.assertTrue(item["reason"])

    def test_items_are_ordered_within_a_line(self):
        line = "Email: a@b.pt, Telefone: +351 912 345 678"
        self.assertEqual(
            found_texts([line]),
            ["a@b.pt", "+351 912 345 678"],
        )


if __name__ == "__main__":
    unittest.main()
