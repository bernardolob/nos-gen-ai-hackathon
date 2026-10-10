"""Guarda da estrutura: todo o código fica em ``submission/solution/``.

O guia de submissão pede o código em ``submission/``. Ter módulos em
``submission/src/`` e outros em ``submission/solution/src/`` obrigava a dois
caminhos de importação e deixava o repositório com duas convenções.
"""

import unittest
from pathlib import Path

SUBMISSION = Path(__file__).resolve().parents[2]
SOLUTION = SUBMISSION / "solution"
IGNORED = {"__pycache__"}


def python_files(root):
    """Ficheiros ``.py`` por baixo de ``root``, sem as pastas ignoradas."""
    return [
        path for path in root.rglob("*.py")
        if not IGNORED.intersection(path.parts)
    ]


class LayoutTest(unittest.TestCase):
    def test_all_python_code_lives_in_solution(self):
        outside = [
            str(path.relative_to(SUBMISSION))
            for path in python_files(SUBMISSION)
            if SOLUTION not in path.parents
        ]
        self.assertEqual(
            outside, [],
            "código fora de submission/solution/: %s" % outside,
        )

    def test_there_is_no_src_folder_next_to_solution(self):
        self.assertFalse((SUBMISSION / "src").exists())

    def test_the_modules_are_in_solution_src(self):
        for name in (
            "pdf_extractor", "detection", "safety_rules", "masking",
            "verification", "report", "categories",
        ):
            self.assertTrue(
                (SOLUTION / "src" / (name + ".py")).exists(), name)


if __name__ == "__main__":
    unittest.main()
