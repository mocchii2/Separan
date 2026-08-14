# Authentication and Secrets — Safe High-Level APIs

Status: **experimental preview implemented**.

Separan exposes purpose-specific primitives instead of asking programs to build
authentication cryptography. The preview includes redacted host-provided
secrets, Basic/Bearer/API-key HTTP authentication, OAuth 2.0 client credentials,
HMAC-SHA256, HS256-only JWT signing and verification, and Argon2id password
hashing. General-purpose cryptographic boundaries are specified separately in
[Cryptography](cryptography.md).

`secret` is distinct from strings and bytes. Display is always `[REDACTED]`,
`string(secret)` is forbidden, and `secret_get` requires a host provider plus an
optional name allowlist. OAuth access tokens remain secrets.

JWT keys must contain at least 32 bytes. The protected header is fixed and
verified, signatures use constant-time comparison, and `exp`/`nbf` use the
runtime clock. Secret or bytes claims are rejected. Password storage uses
Argon2id with a random 16-byte salt; verification retains compatibility with
the earlier alpha scrypt format. Raw SHA-256 is deliberately not a password API.

Diagnostics use `E870`–`E879`, with `secret_error` and `oauth_error` under
`auth_error`. Browser login, authorization-code/device flows, and refresh-token
management remain separate future designs.
