from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PACKAGE_DIR = DIST / "separan-portable"
ARCHIVE = DIST / "separan-portable.zip"
FILES_TO_COPY = [ROOT / "separan.exe", ROOT / "separan.cmd", ROOT / "README.md"]


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

    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(PACKAGE_DIR.iterdir()):
            archive.write(item, arcname=item.name)

    print(f"Created portable ZIP: {ARCHIVE}")


if __name__ == "__main__":
    main()
