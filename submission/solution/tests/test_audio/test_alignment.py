"""Testes do alinhamento (``src/audio/alignment.py``)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audio import alignment  # noqa: E402


class FindMaskedRangesTest(unittest.TestCase):
    def test_no_issues_when_nothing_masked(self):
        ranges = alignment.find_masked_ranges(
            ["Ola mundo"], ["Ola mundo"], [[(0.0, 0.3), (0.4, 0.9)]],
        )
        self.assertEqual(ranges, [])

    def test_one_masked_word(self):
        ranges = alignment.find_masked_ranges(
            ["Nome: Maria"], ["Nome: *"], [[(0.0, 0.4), (0.5, 1.0)]],
        )
        self.assertEqual(ranges, [(0.5, 1.0)])

    def test_several_masked_words_in_one_line(self):
        ranges = alignment.find_masked_ranges(
            ["Nome: Maria Santos"], ["Nome: * *"],
            [[(0.0, 0.4), (0.5, 1.0), (1.0, 1.6)]],
        )
        self.assertEqual(ranges, [(0.5, 1.6)])

    def test_masked_words_across_lines_stay_separate(self):
        ranges = alignment.find_masked_ranges(
            ["Nome: Maria", "Idade: 30"],
            ["Nome: *", "Idade: *"],
            [[(0.0, 0.4), (0.5, 1.0)], [(5.0, 5.4), (5.5, 5.8)]],
        )
        self.assertEqual(ranges, [(0.5, 1.0), (5.5, 5.8)])

    def test_overlapping_ranges_merge(self):
        ranges = alignment.find_masked_ranges(
            ["a b c"], ["* * *"],
            [[(0.0, 0.5), (0.4, 0.9), (0.9, 1.3)]],
        )
        self.assertEqual(ranges, [(0.0, 1.3)])

    def test_line_count_mismatch_raises(self):
        with self.assertRaises(alignment.AlignmentError):
            alignment.find_masked_ranges(
                ["a", "b"], ["a"], [[(0.0, 0.1)], [(0.2, 0.3)]],
            )

    def test_word_times_length_mismatch_raises(self):
        with self.assertRaises(alignment.AlignmentError):
            alignment.find_masked_ranges(
                ["a b"], ["* b"], [[(0.0, 0.1)]],
            )

    def test_masking_that_changed_word_count_raises(self):
        with self.assertRaises(alignment.AlignmentError):
            alignment.find_masked_ranges(
                ["a b"], ["*"], [[(0.0, 0.1), (0.2, 0.3)]],
            )


if __name__ == "__main__":
    unittest.main()
