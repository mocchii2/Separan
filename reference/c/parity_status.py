"""Report native built-in coverage against the Python reference registry."""

from pathlib import Path
from collections import defaultdict
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
    host = re.search(r"static const HostSignature host_signatures\[\].*?\{(.*?)\n \};", source, re.S)
    if host:
        native.update(re.findall(r'^\s*\{"([a-z][a-z_0-9]*)"', host.group(1), re.M))
    native_http = re.search(r"static const HostSignature native_http_signatures\[\].*?\{(.*?)\n\};", source, re.S)
    if native_http:
        native.update(re.findall(r'\{"([a-z][a-z_0-9]*)"', native_http.group(1)))
    errors = re.search(r"static const char \*error_categories\[\].*?\{(.*?)\n \};", source, re.S)
    if errors:
        native.update(re.findall(r'^\s*"([a-z][a-z_0-9]*)"', errors.group(1), re.M))
    reference = set(BUILTINS)
    supported = native & reference
    missing = sorted(reference - native)
    print("Parity mode: independent native C (no CPython delegation)")
    print(f"C dispatch names: {len(supported)} / {len(reference)} Python built-ins")
    categories = defaultdict(lambda: [0, 0])
    for name, builtin in BUILTINS.items():
        implementation = getattr(builtin, "implementation", None)
        module = getattr(implementation, "__module__", "unknown").removeprefix("separan.")
        categories[module][1] += 1
        if name in supported:
            categories[module][0] += 1
    print("Coverage by Python module:")
    for module in sorted(categories):
        present, total = categories[module]
        print(f"  {module}: {present}/{total}")
    print("Missing:")
    for name in missing:
        print(name)


if __name__ == "__main__":
    main()
