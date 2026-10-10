"""Testes das regras de segurança com variações de formato."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import safety_rules  # noqa: E402


def found(line):
    """Devolve só os textos encontrados numa linha."""
    return [item["text"] for item in safety_rules.find_sensitive([line])]


class PhoneTest(unittest.TestCase):
    def test_prefixed_formats(self):
        self.assertEqual(
            found("Telefone: +351-912-345-678"), ["+351-912-345-678"])
        self.assertEqual(
            found("Contacto 00351 912 345 678"), ["00351 912 345 678"])
        self.assertEqual(
            found("Tel: (+351) 912 345 678"), ["(+351) 912 345 678"])
        self.assertEqual(
            found("Fixo: +351 21 345 67 89"), ["+351 21 345 67 89"])

    def test_unprefixed_mobile_and_landline(self):
        self.assertEqual(found("Telefone: 912 345 678"), ["912 345 678"])
        self.assertEqual(found("Tel: 912345678"), ["912345678"])
        self.assertEqual(found("Fixo: 21 345 67 89"), ["21 345 67 89"])

    def test_unprefixed_phone_is_only_probable(self):
        item = safety_rules.find_sensitive(["Tel: 912345678"])[0]
        self.assertEqual(item["confidence"], "provavel")

    def test_prefixed_phone_is_certain(self):
        item = safety_rules.find_sensitive(["Tel: +351912345678"])[0]
        self.assertEqual(item["confidence"], "certo")

    def test_prefixed_phone_is_a_single_item(self):
        self.assertEqual(len(found("Tel: +351 912 345 678")), 1)

    def test_numbers_that_are_not_phones(self):
        self.assertEqual(found("Código 097865413"), [])
        self.assertEqual(found("Exame 12345678901 solicitado"), [])
        self.assertEqual(found("Pressão arterial: 145/90 mmHg"), [])


class EmailTest(unittest.TestCase):
    def test_case_plus_and_subdomain(self):
        self.assertEqual(
            found("Email: Maria.Santos+x@Sub.Dominio.PT."),
            ["Maria.Santos+x@Sub.Dominio.PT"],
        )

    def test_inside_angle_brackets(self):
        self.assertEqual(found("Contacto <a_b@c-d.com>"), ["a_b@c-d.com"])


class IdentityDocumentTest(unittest.TestCase):
    def test_nif_label_variants(self):
        for line in (
            "NIF 097865413",
            "N.I.F.: 097865413",
            "Contribuinte nº 097865413",
            "nif: 097865413",
        ):
            self.assertEqual(found(line), ["097865413"], line)

    def test_nif_with_spaces(self):
        self.assertEqual(found("NIF: 097 865 413"), ["097 865 413"])

    def test_citizen_card_variants(self):
        self.assertEqual(
            found("Cartão de Cidadão nº 12345678-9ZX0"), ["12345678-9ZX0"])
        self.assertEqual(found("CC: 12345678 9 ZX0"), ["12345678 9 ZX0"])
        self.assertEqual(found("BI: 12345678"), ["12345678"])

    def test_social_security_variants(self):
        self.assertEqual(found("NISS: 11223344556"), ["11223344556"])
        self.assertEqual(
            found("Segurança Social nº 11223344556"), ["11223344556"])

    def test_passport(self):
        self.assertEqual(found("Passaporte: AB123456"), ["AB123456"])

    def test_short_labels_do_not_match_inside_words(self):
        self.assertEqual(found("Acesso 12345678 negado"), [])
        self.assertEqual(found("Exibição 12345678"), [])


class BirthDateTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(
            found("Data de Nascimento: 12-03-1978"), ["12-03-1978"])
        self.assertEqual(
            found("Data de nascimento: 1978-03-12"), ["1978-03-12"])
        self.assertEqual(
            found("Nasceu a 12 de março de 1978"), ["12 de março de 1978"])

    def test_other_dates_are_not_flagged(self):
        self.assertEqual(found("Data: 15 de abril de 2025"), [])
        self.assertEqual(found("Consulta marcada para 12/03/2026"), [])


class FinancialTest(unittest.TestCase):
    def test_card_formats(self):
        self.assertEqual(
            found("Cartão: 4111222233334444"), ["4111222233334444"])
        self.assertEqual(
            found("Cartão: 4111-2222-3333-4444"), ["4111-2222-3333-4444"])
        self.assertEqual(
            found("Amex: 3782 822463 10005"), ["3782 822463 10005"])

    def test_cvv_variants(self):
        self.assertEqual(found("CVC 123"), ["123"])
        self.assertEqual(found("Código de segurança: 1234"), ["1234"])

    def test_expiry_variants(self):
        self.assertEqual(found("Validade: 09/2027"), ["09/2027"])
        self.assertEqual(found("exp. 09/27"), ["09/27"])

    def test_policy_variants(self):
        self.assertEqual(found("Apólice: 987654321"), ["987654321"])
        self.assertEqual(found("Apólice n.º 987654321"), ["987654321"])

    def test_iban_is_a_single_item(self):
        self.assertEqual(
            found("IBAN: PT50 0002 0123 1234 5678 9015 4"),
            ["PT50 0002 0123 1234 5678 9015 4"],
        )
        self.assertEqual(
            found("IBAN: PT50000201231234567890154"),
            ["PT50000201231234567890154"],
        )

    def test_income_is_not_flagged(self):
        self.assertEqual(found("Rendimento: €62.500"), [])


class OtherIdentifiersTest(unittest.TestCase):
    def test_postal_code(self):
        self.assertEqual(
            found("Código postal: 2685-001 Sacavém"), ["2685-001"])

    def test_url_without_trailing_punctuation(self):
        self.assertEqual(
            found("Ver https://www.exemplo.pt/perfil/maria."),
            ["https://www.exemplo.pt/perfil/maria"],
        )

    def test_ip_address(self):
        self.assertEqual(found("IP: 192.168.1.10"), ["192.168.1.10"])

    def test_version_number_is_not_an_ip(self):
        self.assertEqual(found("Versão 3.2.1 de 2025"), [])

    def test_reference_number_is_not_flagged(self):
        self.assertEqual(found("Referência: ADM-2025-04-15-089"), [])


class OverlapTest(unittest.TestCase):
    def test_longest_item_wins(self):
        items = safety_rules.find_sensitive(["IBAN: PT50 0002 0123 1234 5678"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "financeiro")

    def test_two_values_on_one_line_keep_order(self):
        line = "Email: a@b.pt, Telefone: +351 912 345 678"
        self.assertEqual(found(line), ["a@b.pt", "+351 912 345 678"])


if __name__ == "__main__":
    unittest.main()
