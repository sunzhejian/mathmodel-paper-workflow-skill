import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fetch_cjk_test_font", ROOT / "scripts/fetch_cjk_test_font.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PAYLOADS = {"font": b"synthetic font bytes", "license": b"synthetic license bytes"}
ASSETS = {"font.ttf": ("https://example.test/font", hashlib.sha256(PAYLOADS["font"]).hexdigest()),
          "OFL.txt": ("https://example.test/license", hashlib.sha256(PAYLOADS["license"]).hexdigest())}


class CJKFontChecks(unittest.TestCase):
    def test_verified_font_and_license_are_cached_without_system_install(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE, "ASSETS", ASSETS):
            root = Path(tmp) / "fonts"
            with patch.object(MODULE.urllib.request, "urlopen", side_effect=lambda url, **kw: io.BytesIO(PAYLOADS[url.rsplit("/", 1)[1]])):
                MODULE.fetch(root)
            self.assertEqual((root / "font.ttf").read_bytes(), PAYLOADS["font"])
            self.assertEqual((root / "OFL.txt").read_bytes(), PAYLOADS["license"])
            with patch.object(MODULE.urllib.request, "urlopen", side_effect=AssertionError("No network on valid cache")):
                self.assertEqual(MODULE.fetch(root), root.resolve())

    def test_bad_download_is_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE, "ASSETS", ASSETS):
            root = Path(tmp) / "fonts"
            with patch.object(MODULE.urllib.request, "urlopen", return_value=io.BytesIO(b"wrong bytes")):
                with self.assertRaisesRegex(ValueError, "verification"):
                    MODULE.fetch(root)
            self.assertFalse(root.exists())

    def test_different_existing_font_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE, "ASSETS", ASSETS):
            root = Path(tmp)
            (root / "font.ttf").write_bytes(b"existing user font")
            with patch.object(MODULE.urllib.request, "urlopen", side_effect=AssertionError("Must not fetch over existing file")):
                with self.assertRaisesRegex(ValueError, "different hash"):
                    MODULE.fetch(root)
            self.assertEqual((root / "font.ttf").read_bytes(), b"existing user font")


if __name__ == "__main__":
    unittest.main()
