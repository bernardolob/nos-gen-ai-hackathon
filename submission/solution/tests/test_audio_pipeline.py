"""Testes do ponto de entrada da censura de áudio (``src/audio_pipeline.py``).

Nenhum teste chama o Gemini nem o ElevenLabs Scribe: ``generate`` e
``call_scribe`` são sempre falsos. ``write_outputs`` chama o ``ffmpeg`` a
sério, sobre um dos sons de censura já no repositório (usado aqui só como
um ficheiro de áudio real qualquer, não pelo seu conteúdo).
"""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))

import audio_pipeline  # noqa: E402

SAMPLE_AUDIO = SOLUTION / "assets" / "censor_sounds" / "censor_1.m4a"
SOUND_PATHS = [SOLUTION / "assets" / "censor_sounds" / "censor_2.m4a"]


def ffmpeg_available():
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def fake_scribe(response):
    def call_scribe(audio_bytes):
        return response
    return call_scribe


def word(text, start, end):
    return {"text": text, "start": start, "end": end, "type": "word"}


NIF_RESPONSE = {"words": [
    word("NIF:", 0.0, 0.3),
    word("123456789", 0.4, 0.9),
]}


class RunTest(unittest.TestCase):
    def test_without_a_model_only_the_rules_apply(self):
        result = audio_pipeline.run(SAMPLE_AUDIO, fake_scribe(NIF_RESPONSE))
        self.assertEqual(result["masked"], ["NIF: *"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["ranges"], [(0.4, 0.9)])

    def test_model_items_also_produce_ranges(self):
        generate = lambda system, content: json.dumps([{  # noqa: E731
            "line": 1, "text": "NIF: 123456789", "category": "identificacao",
            "reason": "nif", "confidence": "certo",
        }])
        result = audio_pipeline.run(
            SAMPLE_AUDIO, fake_scribe(NIF_RESPONSE), generate)
        # labels.py corrige o item do modelo para não ocultar a
        # etiqueta "NIF:" (ver fix/label-in-items), por isso só o valor
        # é mascarado e só o seu intervalo de tempo entra em "ranges".
        self.assertEqual(result["masked"], ["NIF: *"])
        self.assertEqual(result["ranges"], [(0.4, 0.9)])

    def test_nothing_sensitive_gives_no_ranges(self):
        response = {"words": [word("Ola", 0.0, 0.3), word("mundo", 0.4, 0.8)]}
        result = audio_pipeline.run(SAMPLE_AUDIO, fake_scribe(response))
        self.assertEqual(result["masked"], ["Ola mundo"])
        self.assertEqual(result["ranges"], [])


@unittest.skipUnless(ffmpeg_available(), "precisa do ffmpeg instalado")
class WriteOutputsTest(unittest.TestCase):
    def test_writes_audio_submission_and_report(self):
        result = audio_pipeline.run(SAMPLE_AUDIO, fake_scribe(NIF_RESPONSE))
        with tempfile.TemporaryDirectory() as tmp:
            audio_pipeline.write_outputs(
                result, SAMPLE_AUDIO, SOUND_PATHS, tmp)
            out_dir = Path(tmp)
            self.assertTrue(
                (out_dir / audio_pipeline.CENSORED_FILE).exists())
            self.assertEqual(
                (out_dir / "submission.txt").read_text(encoding="utf-8"),
                "NIF: *")
            self.assertIn(
                "Relatório", (out_dir / "report.md").read_text(
                    encoding="utf-8"))


class SummaryTest(unittest.TestCase):
    def test_mentions_the_number_of_ranges(self):
        result = audio_pipeline.run(SAMPLE_AUDIO, fake_scribe(NIF_RESPONSE))
        self.assertIn(
            "intervalos de áudio a substituir: 1",
            audio_pipeline.summary(result))


class MainTest(unittest.TestCase):
    def _run_main(self, argv, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(
            err
        ):
            code = audio_pipeline.main(argv, **kwargs)
        return code, out.getvalue() + err.getvalue()

    def test_dry_run_without_out_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_copy = Path(tmp) / "a.m4a"
            audio_copy.write_bytes(SAMPLE_AUDIO.read_bytes())
            code, output = self._run_main(
                [str(audio_copy), "--no-model"],
                call_scribe=fake_scribe(NIF_RESPONSE))
            self.assertEqual(code, audio_pipeline.EXIT_OK)
            self.assertIn("ensaio", output)
            self.assertEqual(list(Path(tmp).iterdir()), [audio_copy])

    @unittest.skipUnless(ffmpeg_available(), "precisa do ffmpeg instalado")
    def test_out_writes_the_censored_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_copy = Path(tmp) / "a.m4a"
            audio_copy.write_bytes(SAMPLE_AUDIO.read_bytes())
            out_dir = Path(tmp) / "saida"
            code, _ = self._run_main(
                [str(audio_copy), "--no-model", "--out", str(out_dir),
                 "--sounds", str(SOUND_PATHS[0])],
                call_scribe=fake_scribe(NIF_RESPONSE))
            self.assertEqual(code, audio_pipeline.EXIT_OK)
            self.assertTrue(
                (out_dir / audio_pipeline.CENSORED_FILE).exists())

    def test_missing_audio_file_is_a_clean_error(self):
        code, output = self._run_main(
            ["nao-existe.m4a", "--no-model"],
            call_scribe=fake_scribe(NIF_RESPONSE))
        self.assertEqual(code, audio_pipeline.EXIT_ERROR)
        self.assertIn("Erro", output)


if __name__ == "__main__":
    unittest.main()
