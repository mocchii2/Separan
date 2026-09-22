import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_case(binary: Path, directory: Path, name: str, source: str, expect_ok: bool, expected_substr: str | None = None):
    path = directory / f"{name}.sep"
    path.write_text(source, encoding="utf-8")
    proc = subprocess.run([str(binary), "--check", str(path)], capture_output=True, text=True)
    if expect_ok:
        assert proc.returncode == 0, (name, proc.stdout, proc.stderr)
    else:
        assert proc.returncode != 0, (name, proc.stdout, proc.stderr)
        if expected_substr:
            assert expected_substr in proc.stderr, (name, proc.stderr)
    print(f"{name}: ok")


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        binary = directory / "separan_core.exe"
        subprocess.run([
            "gcc", "-std=c11", "-Wall", "-Wextra", "-I", str(ROOT / "include"),
            str(ROOT / "src" / "main.c"), str(ROOT / "src" / "separan_core.c"),
            str(ROOT / "src" / "separan_lexer.c"), str(ROOT / "src" / "separan_files.c"),
            str(ROOT / "src" / "separan_runtime.c"),
            "-o", str(binary), "-lm",
        ], check=True)
        run_cases(binary, directory)


def run_cases(binary: Path, directory: Path) -> None:
    run_case(binary, directory,
        "valid_structures",
        "SEP:main\nif true :check\nprint \"ok\"\nendif:check\nEND_SEP:main\n",
        True,
    )
    run_case(binary, directory,
        "mismatched_label",
        "SEP:main\nif true :check\nendif:wrong\nEND_SEP:main\n",
        False,
        "E104",
    )
    run_case(binary, directory,
        "duplicate_label",
        "SEP:main\nif true :shared\nwhile true :shared\nendwhile:shared\nendif:shared\nEND_SEP:main\n",
        False,
        "E109",
    )
    run_case(binary, directory,
        "unclosed_block",
        "SEP:main\nif true :check\nprint \"x\"\n",
        False,
        "E106",
    )
    run_case(binary, directory,
        "else_label_mismatch",
        "SEP:main\nif true :ok\nelse:wrong\nendif:ok\nEND_SEP:main\n",
        False,
        "E104",
    )
    print("summary: all core syntax checks passed")


if __name__ == "__main__":
    main()
