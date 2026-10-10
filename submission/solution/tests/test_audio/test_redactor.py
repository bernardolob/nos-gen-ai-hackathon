"""Testes da redação do áudio (``src/audio/redactor.py``).

Usa ficheiros reais (os sons de censura já no repositório) e chama o
``ffmpeg`` a sério — não há forma simples de simular cortes e durações de
áudio sem o próprio ffmpeg. Precisa de ``ffmpeg``/``ffprobe`` instalados.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audio import redactor  # noqa: E402

ASSETS = (
    Path(__file__).resolve().parents[2] / "assets" / "censor_sounds"
)
SOUND_1 = ASSETS / "censor_1.m4a"
SOUND_2 = ASSETS / "censor_2.m4a"


def ffmpeg_available():
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@unittest.skipUnless(ffmpeg_available(), "precisa do ffmpeg instalado")
class RedactTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out_path = Path(self.tmp.name) / "out.wav"
        self.original_duration = redactor._probe_duration(SOUND_1)

    def test_no_ranges_keeps_duration(self):
        redactor.redact(SOUND_1, [], [SOUND_2], self.out_path)
        self.assertTrue(self.out_path.exists())
        self.assertAlmostEqual(
            redactor._probe_duration(self.out_path),
            self.original_duration, delta=0.1,
        )

    def test_one_range_keeps_total_duration(self):
        middle = self.original_duration / 2
        redactor.redact(
            SOUND_1, [(0.3, middle)], [SOUND_2], self.out_path,
        )
        self.assertAlmostEqual(
            redactor._probe_duration(self.out_path),
            self.original_duration, delta=0.1,
        )

    def test_range_covering_whole_audio(self):
        redactor.redact(
            SOUND_1, [(0.0, self.original_duration)], [SOUND_2],
            self.out_path,
        )
        self.assertAlmostEqual(
            redactor._probe_duration(self.out_path),
            self.original_duration, delta=0.1,
        )

    def test_sounds_cycle_round_robin(self):
        # Três intervalos, dois sons: o 1º e o 3º usam o mesmo som.
        calls = []
        original_fit = redactor._fit_sound

        def spy(sound_path, target_duration, out_path):
            calls.append(sound_path)
            return original_fit(sound_path, target_duration, out_path)

        redactor._fit_sound = spy
        try:
            redactor.redact(
                SOUND_1,
                [(0.2, 0.4), (0.6, 0.8), (1.0, 1.2)],
                [SOUND_1, SOUND_2],
                self.out_path,
            )
        finally:
            redactor._fit_sound = original_fit
        self.assertEqual(
            calls, [str(SOUND_1), str(SOUND_2), str(SOUND_1)])

    def test_empty_sound_paths_raises(self):
        with self.assertRaises(ValueError):
            redactor.redact(SOUND_1, [(0.0, 0.1)], [], self.out_path)


if __name__ == "__main__":
    unittest.main()
