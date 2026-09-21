import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "separan_core.exe"


def run_case(name: str, source: str, expect_ok: bool, expected_substr: str | None = None):
    path = ROOT / f"{name}.sep"
    path.write_text(source, encoding="utf-8")
    proc = subprocess.run([str(BIN), str(path)], capture_output=True, text=True)
    if expect_ok:
        assert proc.returncode == 0, (name, proc.stdout, proc.stderr)
    else:
        assert proc.returncode != 0, (name, proc.stdout, proc.stderr)
        if expected_substr:
            assert expected_substr in proc.stderr, (name, proc.stderr)
    print(f"{name}: ok")


def main() -> None:
    run_case(
        "valid_structures",
        "SEP:main\nif true :check\nprint \"ok\"\nendif:check\nEND_SEP:main\n",
        True,
    )
    run_case(
        "mismatched_label",
        "SEP:main\nif true :check\nendif:wrong\nEND_SEP:main\n",
        False,
        "E104",
    )
    run_case(
        "duplicate_label",
        "SEP:main\nif true :shared\nwhile true :shared\nendwhile:shared\nendif:shared\nEND_SEP:main\n",
        False,
        "E109",
    )
    run_case(
        "unclosed_block",
        "SEP:main\nif true :check\nprint \"x\"\n",
        False,
        "E106",
    )
    run_case(
        "else_label_mismatch",
        "SEP:main\nif true :ok\nelse:wrong\nendif:ok\nEND_SEP:main\n",
        False,
        "E104",
    )
    print("summary: all core syntax checks passed")


if __name__ == "__main__":
    main()
