"""Report native built-in coverage against the Python reference registry."""

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reference"))

from separan.builtins import BUILTINS


def main():
    source = (Path(__file__).parent / "src" / "separan_runtime.c").read_text(encoding="utf-8")
    match = re.search(r"static int builtin_name\(.*?\{(.*?)\n\}", source, re.S)
    if not match:
        raise SystemExit("Cannot find the C built-in registry")
    native = set(re.findall(r'"([a-z][a-z_0-9]*)"', match.group(1)))
    reference = set(BUILTINS)
    supported = native & reference
    missing = sorted(reference - native)
    print(f"C dispatch names: {len(supported)} / {len(reference)} Python built-ins")
    print("Missing:")
    for name in missing:
        print(name)


if __name__ == "__main__":
    main()
