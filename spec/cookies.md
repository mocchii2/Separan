# HTTP Cookies and Cookie Jars

Status: **experimental preview implemented**.

One-shot cookies use an object; continuing login/session flows use the explicit
mutable `cookie_jar` type. The API includes jar creation, get/set/remove/clear,
and redacted enumeration. HTTP stores `Set-Cookie` automatically and exposes
newly received values as secrets in `response.cookies`; raw `Set-Cookie` is
removed from ordinary response headers.

The jar retains name, secret value, domain, path, expiration/Max-Age, Secure,
HttpOnly, SameSite, and host-only state. Domain, path, expiry, and transport
security are checked before every send. Explicit one-shot cookies never cross
an origin-changing redirect.

Cookie jars are intentionally mutable communication state; this does not make
ordinary objects or lists mutable. Plaintext persistence does not exist. The
only persistence API is `cookie_save_secure` / `cookie_load_secure`.

The version-1 binary container authenticates its magic, version, protection
mode, salt, and 96-bit nonce as AES-256-GCM associated data; ciphertext carries
the full 128-bit tag. Keys are never stored beside ciphertext. Default OS-bound
mode uses an injected user/device keystore. Password mode derives 256 bits with
Argon2id (64 MiB, 3 iterations, 4 lanes, random 16-byte salt). External mode
requires an exact 32-byte secret suitable for KMS/Vault adapters. Algorithms are
not source-selectable. Diagnostics use `E880`–`E889`.
