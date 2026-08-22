"""Build deterministic AWS Lambda ZIP artifacts for Separan source files."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


LAMBDA_DEPENDENCIES = (
    "tzdata>=2025.2",
    "cryptography>=45,<51",
    "argon2-cffi>=23,<26",
    "PyYAML>=6,<7",
)
PLATFORMS = {"x86_64": "manylinux2014_x86_64", "arm64": "manylinux2014_aarch64"}


def _copy_runtime(destination):
    source = Path(__file__).resolve().parent
    target = destination / "separan"
    shutil.copytree(
        source, target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _install_dependencies(destination, architecture, python_version):
    command = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check", "--no-compile", "--only-binary=:all:",
        "--implementation", "cp", "--python-version", python_version,
        "--platform", PLATFORMS[architecture],
        "--target", str(destination), *LAMBDA_DEPENDENCIES,
    ]
    subprocess.run(command, check=True)


def _write_zip(stage, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in stage.rglob("*") if item.is_file()):
            relative = path.relative_to(stage).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_lambda_package(source, output, architecture="x86_64", python_version="313", install_dependencies=True):
    source = Path(source).resolve(); output = Path(output).resolve()
    if source.suffix.lower() != ".sep" or not source.is_file():
        raise ValueError("Lambda application source must be an existing .sep file")
    if architecture not in PLATFORMS: raise ValueError(f"Unsupported Lambda architecture: {architecture}")
    if python_version not in ("312", "313"): raise ValueError("Lambda Python version must be 312 or 313")
    with tempfile.TemporaryDirectory(prefix="separan-lambda-") as temporary:
        stage = Path(temporary)
        _copy_runtime(stage)
        if install_dependencies: _install_dependencies(stage, architecture, python_version)
        shutil.copy2(source, stage / "application.sep")
        (stage / "index.py").write_text(
            "from separan.lambda_entry import handler\n",
            encoding="utf-8", newline="\n",
        )
        _write_zip(stage, output)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="separan lambda-package",
        description="Package a Separan application and its reference runtime for AWS Lambda",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--architecture", choices=tuple(PLATFORMS), default="x86_64")
    parser.add_argument("--python-version", choices=("312", "313"), default="313")
    parser.add_argument("--no-dependencies", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = build_lambda_package(
        args.source, args.output, args.architecture, args.python_version,
        install_dependencies=not args.no_dependencies,
    )
    print(path)
    return 0
