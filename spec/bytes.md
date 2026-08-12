# Bytes — Immutable Binary Values

Status: **experimental preview implemented**.

`bytes` is distinct from strings and number lists. File, HTTP, process, and
secure-random binary data use the same immutable type, with no implicit text
conversion.

The preview provides explicit string conversion (`utf-8`, `utf-16le`,
`utf-16be`, or `ascii`), strict hex and Base64 codecs, byte lookup, strict
slicing, concatenation, shared length/empty checks, and `bytes + bytes`.
Indexes outside `0..length-1`, invalid encodings, malformed codecs, and mixed
bytes/string operations are errors. Binary results are limited to 67,108,864
bytes.

Mutation is intentionally absent. A future mutable `byte_buffer` will be a
separate type. Integer packing will likewise be a separate endian-explicit API.
