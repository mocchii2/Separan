"""Generate the Unicode tables used by the independent C lexer."""

from __future__ import annotations

import argparse
import unicodedata
from pathlib import Path


OUTPUT = Path(__file__).parent / "src" / "separan_unicode_tables.inc"


def _ranges(values):
    result = []
    start = previous = None
    for codepoint in values:
        if start is None:
            start = previous = codepoint
        elif codepoint == previous + 1:
            previous = codepoint
        else:
            result.append((start, previous))
            start = previous = codepoint
    if start is not None:
        result.append((start, previous))
    return result


def generate() -> str:
    codepoints = range(0x80, 0x110000)
    starts = _ranges(cp for cp in codepoints if chr(cp).isidentifier())
    continuations = _ranges(
        cp for cp in range(0x80, 0x110000) if ("_" + chr(cp)).isidentifier()
    )
    nfc_no = _ranges(
        cp
        for cp in range(0x80, 0x110000)
        if unicodedata.normalize("NFC", chr(cp)) != chr(cp)
    )
    combining = [
        (cp, value)
        for cp in range(0x80, 0x110000)
        if (value := unicodedata.combining(chr(cp)))
    ]
    compositions = []
    for cp in range(0x80, 0x110000):
        decomposition = unicodedata.decomposition(chr(cp))
        if not decomposition or decomposition.startswith("<"):
            continue
        parts = [int(value, 16) for value in decomposition.split()]
        if len(parts) == 2 and unicodedata.normalize("NFC", "".join(map(chr, parts))) == chr(cp):
            compositions.append((*parts, cp))
    compositions.sort()

    lines = [
        f"/* Generated from Python Unicode {unicodedata.unidata_version}; inclusive code point ranges. */",
        "typedef struct { unsigned first, last; } UnicodeRange;",
        "typedef struct { unsigned codepoint, value; } UnicodeValue;",
        "typedef struct { unsigned first, second, composite; } UnicodeComposition;",
    ]
    for name, values in (
        ("unicode_identifier_start_ranges", starts),
        ("unicode_identifier_continue_ranges", continuations),
        ("unicode_nfc_no_ranges", nfc_no),
    ):
        lines.append(f"static const UnicodeRange {name}[] = {{")
        lines.extend(f"    {{0x{first:X}u, 0x{last:X}u}}," for first, last in values)
        lines.append("};")
    lines.append("static const UnicodeValue unicode_combining_classes[] = {")
    lines.extend(f"    {{0x{cp:X}u, {value}u}}," for cp, value in combining)
    lines.append("};")
    lines.append("static const UnicodeComposition unicode_compositions[] = {")
    lines.extend(
        f"    {{0x{first:X}u, 0x{second:X}u, 0x{composite:X}u}},"
        for first, second, composite in compositions
    )
    lines.append("};")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the checked-in table differs")
    args = parser.parse_args()
    generated = generate()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="ascii") != generated:
            print(f"Unicode table is stale: run {Path(__file__).name}")
            return 1
        print(f"Unicode {unicodedata.unidata_version} table is current")
        return 0
    OUTPUT.write_text(generated, encoding="ascii", newline="\n")
    print(f"Wrote {OUTPUT} from Unicode {unicodedata.unidata_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
