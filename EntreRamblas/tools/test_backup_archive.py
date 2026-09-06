import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from backup_archive import validate_archive


class ArchiveValidation(unittest.TestCase):
    def make_archive(self, root, extra=None):
        path = Path(root) / "backup.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("dump.sql", "SELECT 1;")
            archive.writestr("manifest.json", '{"major_version":"18.0"}')
            if extra:
                archive.writestr(extra, "bad")
        Path(str(path) + ".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
        return path

    def test_corruption_rejected(self):
        with TemporaryDirectory(prefix="mgs-archive-") as folder:
            path = self.make_archive(folder)
            validate_archive(path)
            with path.open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_archive(path)

    def test_unsafe_paths_rejected(self):
        with TemporaryDirectory(prefix="mgs-archive-") as folder:
            for name in ["filestore/../../escape", "C:/escape", "filestore/../escape"]:
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        validate_archive(self.make_archive(folder, name))

    def test_legacy_requires_explicit_flag(self):
        with TemporaryDirectory(prefix="mgs-archive-") as folder:
            path = self.make_archive(folder)
            Path(str(path) + ".sha256").unlink()
            with self.assertRaises(ValueError):
                validate_archive(path)
            validate_archive(path, allow_legacy=True)


if __name__ == "__main__":
    unittest.main()
