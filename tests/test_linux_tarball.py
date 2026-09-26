import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "reference" / "c" / "build_linux_tarball.py"


class LinuxTarballTests(unittest.TestCase):
    def test_packages_architecture_labels_with_shared_install_makefile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "native"
            output = root / "dist"
            binary.write_bytes(b"\x7fELF" + b"test executable")

            for architecture in ("x86_64", "aarch64"):
                result = subprocess.run(
                    [sys.executable, str(BUILDER), "--binary", str(binary), "--architecture", architecture,
                     "--output-dir", str(output)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

                archive_path = output / f"separan-linux-{architecture}.tar.gz"
                with tarfile.open(archive_path, "r:gz") as archive:
                    self.assertEqual(set(archive.getnames()), {"Makefile", "README.md", "separan"})
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

    @unittest.skipIf(os.name == "nt", "POSIX install target is Linux-only")
    def test_make_install_installs_prebuilt_binary_with_destdir(self):
        make = shutil.which("make")
        if not make:
            self.skipTest("make is required")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "dist"
            binary = root / "separan"
            binary.write_bytes(b"\x7fELF" + b"test executable")
            subprocess.run([sys.executable, str(BUILDER), "--binary", str(binary), "--output-dir", str(output)], check=True)
            package = output / "separan-linux-x86_64"
            result = subprocess.run(
                [make, "install", f"DESTDIR={root / 'stage'}", "PREFIX=/usr"],
                cwd=package, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = root / "stage" / "usr" / "bin" / "separan"
            self.assertEqual(installed.read_bytes(), binary.read_bytes())


if __name__ == "__main__":
    unittest.main()