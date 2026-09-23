"""Check that multipart publication preserves the already-verified archives."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "Scripts/package_release_transport.py"
SPEC = importlib.util.spec_from_file_location("release_transport", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseTransportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.assets = self.root / "assets"
        self.output = self.root / "parts"
        self.assets.mkdir()
        records = []
        for name in sorted(MODULE.ARCHIVES):
            data = (name + " preserved bytes").encode()
            (self.assets / name).write_bytes(data)
            records.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        (self.assets / "distribution_manifest.json").write_text(json.dumps({
            "release_tag": "fsa-research-v2-2026-09-22", "assets": records,
        }))

    def test_parts_reassemble_exactly_and_repeat_does_not_change_sources(self):
        original = {p.name: p.read_bytes() for p in self.assets.iterdir()}
        result = MODULE.package_transport(self.assets, self.output, 11)
        for archive in result["archives"]:
            data = b"".join(
                ((self.assets if part["name"] == MODULE.WHOLE_ARCHIVE else self.output) / part["name"]).read_bytes()
                for part in archive["parts"]
            )
            self.assertEqual(data, original[archive["name"]])
            self.assertEqual(hashlib.sha256(data).hexdigest(), archive["sha256"])
        self.assertEqual(MODULE.package_transport(self.assets, self.output, 11), result)
        self.assertEqual({p.name: p.read_bytes() for p in self.assets.iterdir()}, original)

    def test_changed_source_rejected_before_output_is_created(self):
        (self.assets / MODULE.WHOLE_ARCHIVE).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differs"):
            MODULE.package_transport(self.assets, self.output, 11)
        self.assertFalse(self.output.exists())

    def test_conflicting_piece_is_not_overwritten(self):
        result = MODULE.package_transport(self.assets, self.output, 11)
        part = next(a["parts"][0] for a in result["archives"] if a["name"] != MODULE.WHOLE_ARCHIVE)
        path = self.output / part["name"]
        path.write_bytes(b"preserve conflicting file")
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            MODULE.package_transport(self.assets, self.output, 11)
        self.assertEqual(path.read_bytes(), b"preserve conflicting file")


if __name__ == "__main__":
    unittest.main()
