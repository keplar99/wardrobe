import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "backend"))

from db import apply_schema  # noqa: E402


class CatalogImportSchemaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_apply_schema_creates_import_tables(self):
        apply_schema(self.conn)

        table_names = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertIn("import_batches", table_names)
        self.assertIn("import_images", table_names)
        self.assertIn("draft_items", table_names)
        self.assertIn("draft_item_images", table_names)
        self.assertIn("draft_observations", table_names)


if __name__ == "__main__":
    unittest.main()
