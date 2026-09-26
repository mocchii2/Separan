import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "reference" / "c" / "build_linux_tarball.py"


class LinuxTarballTests(unittest.TestCase):
    def test_packages_only_elf_as_executable_named_separan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "native"
            output = root / "dist"
            binary.write_bytes(b"\x7fELF" + b"test executable")

            result = subprocess.run(
                [sys.executable, str(BUILDER), "--binary", str(binary), "--output-dir", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            archive_path = output / "separan-linux-x86_64.tar.gz"
            with tarfile.open(archive_path, "r:gz") as archive:
                self.assertEqual(set(archive.getnames()), {"README.md", "separan"})
                executable = archive.getmember("separan")
                self.assertTrue(executable.mode & 0o111)
                self.assertEqual(archive.extractfile(executable).read(), binary.read_bytes())

            windows_binary = root / "windows.exe"
            windows_binary.write_bytes(b"MZ" + b"not an ELF executable")
            rejected = subprocess.run(
                [sys.executable, str(BUILDER), "--binary", str(windows_binary), "--output-dir", str(root / "bad-dist")],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("non-ELF", rejected.stderr)


if __name__ == "__main__":
    unittest.main()