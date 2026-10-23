"""Focused probe extraction tests; not production ART conformance tests."""

from io import BytesIO
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from guest import extract


class GuestExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "work" / "input"

    def archive(self, entries):
        result = BytesIO()
        with zipfile.ZipFile(result, "w") as out:
            for name, data in entries:
                out.writestr(name, data)
        result.seek(0)
        return result

    def unpack(self, entries, **kwargs):
        return extract(
            self.archive(entries),
            self.root,
            maximum_bytes=kwargs.get("maximum_bytes", 1024),
            maximum_entries=kwargs.get("maximum_entries", 100),
        )

    def test_valid_archive_preserves_hidden_files_and_executable_bit(self):
        script = zipfile.ZipInfo("tests/run.sh")
        script.external_attr = (stat.S_IFREG | 0o755) << 16
        self.assertEqual(self.unpack([(".hidden", b"data"), (script, b"true")]), 8)
        self.assertEqual((self.root / ".hidden").read_bytes(), b"data")
        self.assertEqual((self.root / "tests/run.sh").stat().st_mode & 0o777, 0o555)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o555)
        # TemporaryDirectory needs write access to remove this test fixture.
        self.root.chmod(0o755)
        (self.root / "tests").chmod(0o755)

    def test_traversal_and_ambiguous_names_are_rejected(self):
        for name in (
            "../outside",
            "/outside",
            "a/../outside",
            "a//b",
            "C:/x",
            "a\\b",
            "./a",
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "archive_entry_invalid"):
                    self.unpack([(name, b"x")])
                self.root.rmdir()
        self.assertFalse((self.root.parent / "outside").exists())

    def test_symlink_is_rejected_before_following_target(self):
        entry = zipfile.ZipInfo("escape")
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, "archive_entry_invalid"):
            self.unpack([(entry, b"/tmp")])
        self.assertFalse((self.root / "escape").exists())

    def test_actual_decompressed_bytes_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "archive_expansion_limit"):
            self.unpack([("big", b"a" * 100)], maximum_bytes=10)
        self.assertLessEqual((self.root / "big").stat().st_size, 10)

    def test_entry_count_checked_before_writing_files(self):
        with self.assertRaisesRegex(ValueError, "archive_entry_limit"):
            self.unpack([("a", b"a"), ("b", b"b")], maximum_entries=1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_file_rejected_without_overwriting(self):
        with self.assertRaisesRegex(ValueError, "archive_entry_invalid"):
            self.unpack([("a", b"a"), ("a", b"b")])
        self.assertEqual((self.root / "a").read_bytes(), b"a")


if __name__ == "__main__":
    unittest.main()
