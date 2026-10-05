"""Standard-library checks for the GitHub Pages export."""
import json
import gzip
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist"


def read(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    parts = sorted(path.parent.glob(path.name + ".gz.part*"))
    if parts:
        return json.loads(gzip.decompress(b"".join(part.read_bytes() for part in parts)).decode("utf-8"))
    raise FileNotFoundError(path)


class StaticExportTests(unittest.TestCase):
    def test_geometry_and_chunks(self):
        manifest = read(OUT / "data/geo-manifest.json")
        for level in ("province", "city", "district", "south_china_sea"):
            original = read(ROOT / f"data/geo/{level}.json")["features"]
            exported = {}
            for chunk in manifest["levels"][level]["chunks"]:
                for feature in read(OUT / "data" / chunk["path"])["features"]:
                    exported[feature["properties"]["id"]] = feature
            self.assertEqual(len(original), manifest["levels"][level]["canonical_count"])
            for feature in original:
                self.assertEqual(exported[feature["properties"]["id"]]["geometry"], feature["geometry"])

    def test_static_entrypoint_has_no_ai_runtime(self):
        page = (OUT / "index.html").read_text(encoding="utf-8")
        self.assertIn("static/data-client-v11.js", page)
        self.assertNotIn("src=\"/static/", page)
        self.assertNotIn("href=\"/static/", page)
        self.assertNotIn("ai-panel", page)
        self.assertNotIn("test-panel", page)
        self.assertNotIn("fetch(\"/api/ai", page)
        self.assertFalse((OUT / "static/ai-panel-local.js").exists())
        self.assertTrue((OUT / "data/history/battles_post1949.json").exists())
        self.assertTrue((OUT / "data/world.json").exists())


if __name__ == "__main__":
    unittest.main()
