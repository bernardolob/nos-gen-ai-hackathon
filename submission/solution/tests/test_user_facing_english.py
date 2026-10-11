"""Everything the review screen can show comes in English.

The backend's messages (the ``detail`` of an error, the ``error`` of a failed
image or video job) and the reasons of the regions it makes are shown as they
are in the UI, which is in English by the team's decision. The code and the
documentation stay in Portuguese; only these strings are English.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

MODULES = ("user_validation.py", "media/pipeline.py", "media/analyzer.py",
           "media/capabilities.py", "media/regions.py")
ERRORS = {"ReviewError", "MediaError", "MediaValidationError",
          "MediaAnalysisError", "MediaConfigurationError"}
# Sent to the model (not shown on the site) with the reviewer's feedback.
NOT_SHOWN = {"INSTRUCTIONS_HEADER"}
PORTUGUESE = re.compile(
    r"[ãõçáéíóúâêôà]|\b(não|para|uma?|ficheiro|erro|tente|envie)\b",
    re.IGNORECASE)


def strings(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return strings(node.left)
    return []


def user_facing_strings(path):
    tree = ast.parse((SRC / path).read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = (node.func.id if isinstance(node.func, ast.Name)
                    else getattr(node.func, "attr", None))
            if name in ERRORS:
                for arg in node.args:
                    found += [(name, text) for text in strings(arg)]
        if isinstance(node, ast.Assign) and isinstance(
                node.targets[0], ast.Name):
            target = node.targets[0].id
            if target.isupper() and target not in NOT_SHOWN and (
                    target.endswith(("_FAILED", "_OFF", "_PDF"))
                    or target in {"NO_SPEECH", "INITIAL_TOO_LONG"}):
                found += [(target, text) for text in strings(node.value)]
        if isinstance(node, ast.keyword) and node.arg == "reason":
            found += [("reason", text) for text in strings(node.value)]
    return found


class EnglishOnTheSiteTest(unittest.TestCase):
    def test_no_message_or_reason_is_in_portuguese(self):
        checked = 0
        for module in MODULES:
            for where, text in user_facing_strings(module):
                checked += 1
                self.assertIsNone(
                    PORTUGUESE.search(text),
                    "%s: %s: %r" % (module, where, text))
        self.assertGreater(checked, 50)

    def test_the_media_prompt_asks_for_english_reasons(self):
        from media.analyzer import MEDIA_PROMPT, RESIDUAL_PROMPT
        self.assertIn("reason in English", MEDIA_PROMPT)
        self.assertIn("reason in English", RESIDUAL_PROMPT)

    def test_the_fixed_messages_read_as_english(self):
        import user_validation
        for name in ("MODEL_FAILED", "AUDIO_OFF", "TRANSCRIBE_FAILED",
                     "NO_SPEECH", "ALIGN_FAILED", "REDACT_FAILED",
                     "PDF_FAILED", "PREVIEW_FAILED", "NO_PDF"):
            text = getattr(user_validation, name)
            self.assertRegex(text, r"^[A-Za-z0-9 ,.;:()'/_-]+$", name)

    def test_the_face_detector_reason_is_english(self):
        source = (SRC / "media" / "pipeline.py").read_text(encoding="utf-8")
        self.assertIn("Potentially identifiable face.", source)
        self.assertNotIn("Rosto potencialmente", source)


if __name__ == "__main__":
    unittest.main()
