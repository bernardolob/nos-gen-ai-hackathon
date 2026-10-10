"""Testes da transcrição (``src/audio/transcriber.py``).

Nenhum teste toca na rede ou na API real: ``call_scribe`` é sempre uma
função falsa, como ``detection.detect`` já testa sem o Gemini.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audio import transcriber  # noqa: E402


def word(text, start, end, type_="word"):
    return {"text": text, "start": start, "end": end, "type": type_}


def fake_scribe(response):
    """Devolve um ``call_scribe`` que ignora o áudio e responde fixo."""
    def call_scribe(audio_bytes):
        return response
    return call_scribe


class TranscribeTest(unittest.TestCase):
    def _run(self, response):
        # Um ficheiro numa pasta temporária: um NamedTemporaryFile aberto
        # não se pode reabrir por nome no Windows.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "audio.m4a"
            path.write_bytes(b"conteudo de audio qualquer")
            return transcriber.transcribe(
                str(path), fake_scribe(response))

    def test_single_sentence_becomes_one_line(self):
        lines, times = self._run({"words": [
            word("Ola", 0.0, 0.3),
            word("mundo.", 0.4, 0.9),
        ]})
        self.assertEqual(lines, ["Ola mundo."])
        self.assertEqual(times, [[(0.0, 0.3), (0.4, 0.9)]])

    def test_two_sentences_become_two_lines(self):
        lines, _ = self._run({"words": [
            word("Ola.", 0.0, 0.3),
            word("Tudo", 0.4, 0.6),
            word("bem?", 0.7, 1.0),
        ]})
        self.assertEqual(lines, ["Ola.", "Tudo bem?"])

    def test_spacing_and_audio_event_entries_are_skipped(self):
        lines, times = self._run({"words": [
            word("Ola", 0.0, 0.3),
            word(" ", 0.3, 0.4, type_="spacing"),
            word("[riso]", 0.4, 0.6, type_="audio_event"),
            word("mundo.", 0.7, 1.0),
        ]})
        self.assertEqual(lines, ["Ola mundo."])
        self.assertEqual(times, [[(0.0, 0.3), (0.7, 1.0)]])

    def test_long_sentence_without_punctuation_is_capped(self):
        words = [
            word("palavra%d" % i, i, i + 0.5)
            for i in range(25)
        ]
        lines, times = self._run({"words": words})
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(lines[0].split()), 20)
        self.assertEqual(len(lines[1].split()), 5)
        self.assertEqual(len(times[0]), 20)
        self.assertEqual(len(times[1]), 5)

    def test_missing_words_key_raises(self):
        with self.assertRaises(transcriber.TranscriptionError):
            self._run({"not_words": []})

    def test_malformed_word_raises(self):
        with self.assertRaises(transcriber.TranscriptionError):
            self._run({"words": [{"text": "Ola", "type": "word"}]})

    def test_zero_duration_word_raises(self):
        with self.assertRaises(transcriber.TranscriptionError):
            self._run({"words": [word("Ola", 1.0, 1.0)]})

    def test_empty_response_gives_no_lines(self):
        lines, times = self._run({"words": []})
        self.assertEqual(lines, [])
        self.assertEqual(times, [])


if __name__ == "__main__":
    unittest.main()
