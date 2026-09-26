from __future__ import annotations

import argparse
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
EXECUTABLE_NAME = "separan"


def main() -> None:
    parser = argparse.ArgumentParser(description="Package a native Linux Separan executable.")
    parser.add_argument("--binary", type=Path, default=ROOT / EXECUTABLE_NAME,
                        help="Linux executable to package (default: reference/c/separan)")
    parser.add_argument("--output-dir", type=Path, default=DIST,
                        help="directory for the package directory and tarball")
    args = parser.parse_args()

    binary = args.binary.resolve()
    output_dir = args.output_dir.resolve()
    package_dir = output_dir / "separan-linux-x86_64"
    archive_path = output_dir / "separan-linux-x86_64.tar.gz"
    if not binary.is_file():
        raise SystemExit(f"Linux executable not found: {binary}")
    with binary.open("rb") as executable_stream:
        if executable_stream.read(4) != b"\x7fELF":
            raise SystemExit(f"Refusing to package a non-ELF executable as Linux: {binary}")

    output_dir.mkdir(exist_ok=True, parents=True)
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    executable = package_dir / EXECUTABLE_NAME
    shutil.copy2(binary, executable)
    executable.chmod(executable.stat().st_mode | 0o111)
    shutil.copy2(ROOT / "README.md", package_dir / "README.md")

    if archive_path.exists():
        archive_path.unlink()

    with tarfile.open(archive_path, "w:gz") as archive:
        for item in sorted(package_dir.iterdir()):
            metadata = archive.gettarinfo(str(item), arcname=item.name)
            if item == executable:
                metadata.mode = 0o755
            with item.open("rb") as stream:
                archive.addfile(metadata, stream)

    print(f"Created Linux tarball: {archive_path}")


if __name__ == "__main__":
    main()