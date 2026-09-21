from __future__ import annotations

import os
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PACKAGE_DIR = DIST / "separan-linux-x86_64"
ARCHIVE = DIST / "separan-linux-x86_64.tar.gz"
FILES_TO_COPY = [ROOT / "separan.exe", ROOT / "README.md"]


def main() -> None:
    DIST.mkdir(exist_ok=True, parents=True)
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    for source in FILES_TO_COPY:
        if source.exists():
            shutil.copy2(source, PACKAGE_DIR / source.name)

    if ARCHIVE.exists():
        ARCHIVE.unlink()

    with tarfile.open(ARCHIVE, "w:gz") as archive:
        for item in sorted(PACKAGE_DIR.iterdir()):
            archive.add(item, arcname=item.name)

    print(f"Created Linux tarball: {ARCHIVE}")


if __name__ == "__main__":
    main()
