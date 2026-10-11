"""O esquema JSON da deteção: uma só fonte para o gateway e o SDK."""

import json
import re
import unittest
from pathlib import Path

import detection
from categories import CATEGORY_NAMES, CONFIDENCE_LEVELS

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "cloudflare" / "worker.ts"


class DetectionSchemaTest(unittest.TestCase):
    def setUp(self):
        self.schema = detection.load_response_schema()
        self.item = self.schema["items"]

    def test_it_is_a_list_of_objects(self):
        self.assertEqual(self.schema["type"], "ARRAY")
        self.assertEqual(self.item["type"], "OBJECT")

    def test_categories_and_confidence_are_the_projects(self):
        props = self.item["properties"]
        self.assertEqual(
            props["category"]["enum"], list(CATEGORY_NAMES))
        self.assertEqual(
            props["confidence"]["enum"], list(CONFIDENCE_LEVELS))

    def test_the_fields_are_the_items_of_the_contract(self):
        props = set(self.item["properties"])
        self.assertEqual(
            props, {"line", "text", "category", "reason", "confidence",
                    "occurrence", "visible"})
        self.assertEqual(
            self.item["required"], ["line", "text", "category", "confidence"])
        self.assertEqual(set(self.item["propertyOrdering"]), props)

    def test_nothing_in_it_can_be_null(self):
        self.assertNotIn("nullable", json.dumps(self.schema))

    def test_the_worker_uses_this_very_file(self):
        source = WORKER.read_text(encoding="utf-8")
        self.assertTrue(re.search(
            r'import detectionSchema from "[./]*submission/solution/'
            r'detection_schema\.json"', source))
        self.assertIn("responseSchema: RESPONSE_FORMATS[format]", source)

    def test_every_field_the_detection_reads_is_in_the_schema(self):
        # An item the schema allows must be one detection can parse.
        sample = {"line": 1, "text": "x", "category": "saude",
                  "confidence": "certo", "occurrence": 2, "visible": True}
        items, warnings = detection.parse_response(
            json.dumps([sample]), ["texto x"])
        self.assertEqual(warnings, [])
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
