"""A saída em PDF: o original com as palavras mascaradas apagadas."""

import tempfile
import unittest
from pathlib import Path

import fitz

import pdf_output
import pipeline

TEXT = [
    "Relatório de Admissão",
    "Nome: Maria Santos, NIF 245789123.",
    "Diagnóstico: diabetes tipo 2",
]


def make_pdf(path, lines=TEXT, second_page=None):
    doc = fitz.open()
    for chunk in (lines, second_page):
        if chunk is None:
            continue
        page = doc.new_page()
        for number, line in enumerate(chunk):
            page.insert_text((72, 100 + 24 * number), line, fontsize=12)
    doc.save(str(path))
    doc.close()


def words_of(path):
    with fitz.open(str(path)) as doc:
        return [w[4] for page in doc for w in page.get_text("words")]


class PdfOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.source = self.dir / "in.pdf"
        self.out = self.dir / "out.pdf"

    def run_it(self, lines, masked):
        return pdf_output.anonymize_pdf(self.source, lines, masked, self.out)

    def test_masked_words_are_removed_from_the_pdf_not_just_covered(self):
        make_pdf(self.source)
        lines = pipeline.read_lines(self.source)
        masked = [
            lines[0],
            "Nome: * *, NIF *.",
            "Diagnóstico: * tipo 2",
        ]
        info = self.run_it(lines, masked)
        words = words_of(self.out)
        for secret in ("Maria", "Santos,", "245789123.", "diabetes"):
            self.assertNotIn(secret, words)
        self.assertEqual(info["words"], 4)
        self.assertEqual(info["whole_lines"], 0)
        raw = self.out.read_bytes()
        self.assertNotIn(b"Maria", raw)
        self.assertNotIn(b"245789123", raw)

    def test_punctuation_next_to_a_mask_stays(self):
        make_pdf(self.source)
        lines = pipeline.read_lines(self.source)
        masked = [lines[0], "Nome: *, NIF *.", lines[2]]
        # "Maria Santos," is two words: only the second is masked here.
        masked[1] = "Nome: Maria *, NIF *."
        self.run_it(lines, masked)
        words = words_of(self.out)
        self.assertIn("Maria", words)
        self.assertIn("*,", words)
        self.assertIn("*.", words)

    def test_the_rest_of_the_page_is_untouched(self):
        make_pdf(self.source)
        lines = pipeline.read_lines(self.source)
        masked = [lines[0], "Nome: * *, NIF *.", lines[2]]
        self.run_it(lines, masked)
        words = words_of(self.out)
        for kept in ("Relatório", "Admissão", "Nome:", "NIF", "tipo", "2"):
            self.assertIn(kept, words)
        with fitz.open(str(self.out)) as doc:
            self.assertEqual(len(doc), 1)

    def test_a_line_that_does_not_match_is_covered_whole(self):
        make_pdf(self.source)
        lines = pipeline.read_lines(self.source)
        # The model's line has a different number of words than the PDF's.
        masked = [lines[0], "Nome: *", lines[2]]
        info = self.run_it(lines, masked)
        self.assertEqual(info["whole_lines"], 1)
        words = words_of(self.out)
        self.assertNotIn("Maria", words)
        self.assertNotIn("245789123.", words)

    def test_two_pages(self):
        make_pdf(self.source, TEXT, ["Outra página", "Rui Pinto"])
        lines = pipeline.read_lines(self.source)
        masked = list(lines)
        masked[-1] = "* *"
        info = self.run_it(lines, masked)
        self.assertEqual(info["pages"], 1)
        self.assertNotIn("Pinto", words_of(self.out))

    def test_nothing_to_hide_gives_the_same_words(self):
        make_pdf(self.source)
        lines = pipeline.read_lines(self.source)
        self.run_it(lines, list(lines))
        self.assertEqual(sorted(words_of(self.out)),
                         sorted(words_of(self.source)))

    def test_a_mismatch_between_lines_and_pdf_is_refused(self):
        make_pdf(self.source)
        with self.assertRaises(pdf_output.PdfOutputError):
            self.run_it(["só uma linha"], ["só uma linha"])

    def test_a_pdf_that_still_has_the_secret_fails_the_check(self):
        make_pdf(self.source)
        masked = ["Relatório de Admissão", "Nome: * *, NIF *.",
                  "Diagnóstico: * tipo 2"]
        # The original, unredacted, is not what the masked text says.
        with self.assertRaises(pdf_output.PdfOutputError):
            pdf_output.check_pdf(self.source, masked)

    def test_an_unreadable_source_is_refused_without_details(self):
        self.source.write_bytes(b"not a pdf")
        with self.assertRaises(pdf_output.PdfOutputError) as raised:
            self.run_it(["x"], ["*"])
        self.assertNotIn("not a pdf", str(raised.exception))

    def test_an_encrypted_pdf_is_refused(self):
        make_pdf(self.source)
        with fitz.open(str(self.source)) as doc:
            doc.save(str(self.dir / "locked.pdf"),
                     encryption=fitz.PDF_ENCRYPT_AES_256,
                     user_pw="x", owner_pw="y")
        with self.assertRaises(pdf_output.PdfOutputError):
            pdf_output.anonymize_pdf(
                self.dir / "locked.pdf", ["a"], ["*"], self.out)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.source = self.dir / "in.pdf"
        make_pdf(self.source)

    def test_pdf_flag_writes_the_pdf_next_to_the_outputs(self):
        out = self.dir / "out"
        code = pipeline.main(
            [str(self.source), "--no-model", "--out", str(out), "--pdf"])
        self.assertIn(code, (pipeline.EXIT_OK, pipeline.EXIT_VERIFICATION))
        self.assertTrue((out / pipeline.PDF_FILE).is_file())
        # The safety rules alone hide the tax number.
        self.assertNotIn("245789123.", words_of(out / pipeline.PDF_FILE))

    def test_pdf_flag_needs_out_and_a_pdf(self):
        self.assertEqual(
            pipeline.main([str(self.source), "--no-model", "--pdf"]),
            pipeline.EXIT_ERROR)
        text = self.dir / "a.txt"
        text.write_text("Nome: Maria\n", encoding="utf-8")
        self.assertEqual(
            pipeline.main([str(text), "--no-model", "--out",
                           str(self.dir / "o"), "--pdf"]),
            pipeline.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
