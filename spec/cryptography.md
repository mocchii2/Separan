# Cryptography — Safe Paths and Explicit Boundaries

Status: **experimental preview implemented in v0.2.0-alpha.3**.

Separan separates purpose-specific safe APIs from the small set of primitives
needed for protocols. It does not expose cipher modes or algorithm-selection
strings. MD5, SHA-1, DES, RC4, AES-ECB, unauthenticated encryption, and custom
nonce input are deliberately absent.

## Digests, HMAC, and encodings

```separan
digest = sha256_hash(data)
signature = sha256_hmac(key, data)

hex = bytes_to_hexadecimal(digest)
digest = hexadecimal_to_bytes(hex)

text = bytes_to_base64(data)
data = base64_to_bytes(text)
```

The implemented digest functions are `sha256_hash`, `sha512_hash`,
`sha3_256_hash`, and `sha3_512_hash`. HMAC is available as `sha256_hmac` and
`sha512_hmac`. All return immutable `bytes`, never an implicitly formatted
string. Existing `hmac_sha256`, `hex_encode`/`hex_decode`, and
`base64_encode`/`base64_decode` names remain compatibility aliases.

String inputs at this explicit crypto boundary are UTF-8 encoded. `bytes` and
`secret` are accepted directly. `constant_time_equal(left, right)` compares
secret-compatible inputs without value-dependent short-circuiting.

## Password storage

```separan
stored = password_hash(password)
ok = password_verify(candidate, stored)
```

New password hashes use Argon2id with a random 16-byte salt and a versioned PHC
string. The runtime currently fixes memory to 64 MiB, iterations to 3,
parallelism to 4, and output to 32 bytes. `password_verify` also recognizes the
old Separan alpha scrypt format so an upgrade does not invalidate existing
hashes. General digest functions are not password-storage APIs.

## Authenticated encryption

For an existing exact 32-byte key:

```separan
encrypted = encrypt_authenticated(key, plaintext)
plaintext = decrypt_authenticated(key, encrypted)
```

The key must be `secret` or `bytes`; string keys are rejected. AES-256-GCM is
the only scheme. Encryption generates a fresh 12-byte nonce internally and
returns an opaque, versioned `bytes` container containing the algorithm-owned
metadata and authentication tag. The runtime authenticates the header as
associated data. A changed container or wrong key raises
`crypto_authentication_error`; it never returns corrupted plaintext.

The container preserves whether plaintext was string, bytes, or secret. A
decrypted secret therefore remains redacted.

Password-based encryption is the safer portable path when no key store exists:

```separan
encrypted = encrypt_with_password(password, plaintext)
plaintext = decrypt_with_password(password, encrypted)
```

It generates its own 16-byte salt and nonce, derives an AES-256 key with the
fixed Argon2id profile, and records versioned parameters in the authenticated
container. `derive_key_from_password(password, salt_bytes)` is available for
protocol integration and returns `secret`; callers must provide at least 16
bytes of salt.

`secure_random_number(minimum, maximum)` is the readable inclusive integer
name for `secure_random_int`; `secure_random_bytes(length)` remains the key and
nonce material source for application protocols. Secure randomness cannot be
seeded.

Diagnostics use `E920`–`E929`. `crypto_authentication_error` is a child of
`crypto_error` for labeled `try`/`catch` handling.
