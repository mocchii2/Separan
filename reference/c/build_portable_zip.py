from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent.parent
DIST = ROOT / "dist"
PACKAGE_DIR = DIST / "separan-portable"
ARCHIVE = DIST / "separan-portable.zip"
FILES_TO_COPY = [
    ROOT / "separan.exe",
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "README.ja.md",
    REPO_ROOT / "docs" / "philosophy.md",
    REPO_ROOT / "docs" / "philosophy.ja.md",
    REPO_ROOT / "docs" / "ai-integration.md",
    REPO_ROOT / "docs" / "ai-integration.ja.md",
]
DIRECTORIES_TO_COPY = [REPO_ROOT / "spec"]


def main() -> None:
    DIST.mkdir(exist_ok=True, parents=True)
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    for source in FILES_TO_COPY:
        if source.exists():
            shutil.copy2(source, PACKAGE_DIR / source.name)
    for source in DIRECTORIES_TO_COPY:
        if source.exists():
            shutil.copytree(source, PACKAGE_DIR / source.name)

    if ARCHIVE.exists():
        ARCHIVE.unlink()

    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(PACKAGE_DIR.rglob("*")):
            archive.write(item, arcname=item.relative_to(PACKAGE_DIR).as_posix())

    print(f"Created portable ZIP: {ARCHIVE}")


if __name__ == "__main__":
    main()
