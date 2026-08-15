# Authentication and Secrets — Safe High-Level APIs

Status: **experimental preview implemented**.

Separan exposes purpose-specific primitives instead of asking programs to build
authentication cryptography. The preview includes redacted host-provided
secrets, Basic/Bearer/API-key HTTP authentication, OAuth 2.0 client credentials,
HMAC-SHA256, HS256-only JWT signing and verification, and Argon2id password
hashing. General-purpose cryptographic boundaries are specified separately in
[Cryptography](cryptography.md).

`secret_from_environment(name)` provides an explicit redacted alternative to
ordinary `env_get` for credentials such as SMTP passwords. It uses the same
host-controlled environment read capability and variable-name allowlist.

`secret` is distinct from strings and bytes. Display is always `[REDACTED]`,
`string(secret)` is forbidden, and `secret_get` requires a host provider plus an
optional name allowlist. `secret_from_environment` uses the environment
capability instead. OAuth access tokens remain secrets.

JWT keys must contain at least 32 bytes. The protected header is fixed and
verified, signatures use constant-time comparison, and `exp`/`nbf` use the
runtime clock. Secret or bytes claims are rejected. Password storage uses
Argon2id with a random 16-byte salt; verification retains compatibility with
the earlier alpha scrypt format. Raw SHA-256 is deliberately not a password API.

Diagnostics use `E870`–`E879`, with `secret_error` and `oauth_error` under
`auth_error`. Browser login, authorization-code/device flows, and refresh-token
management remain separate future designs.

```separan
client_secret = secret_from_environment("OAUTH_CLIENT_SECRET")

token = oauth_client_credentials("https://auth.example.com/oauth/token", "monitor-client", client_secret, scope = "monitor.read alerts.write")

response = http_request("https://api.example.com/status", auth = bearer_auth(token.access_token))
```

The token endpoint must be an absolute HTTPS URL without embedded credentials
or a fragment. Client identifiers and secrets are form-encoded before HTTP
Basic client authentication. Successful responses must contain a visible-ASCII
Bearer access token, which remains a redacted `secret`. A refresh token in a
Client Credentials response is rejected instead of being silently retained or
discarded. Error diagnostics expose only a validated OAuth `error` code, never
an arbitrary server-provided `error_description`.

See [`examples/oauth_client_credentials.sep`](../examples/oauth_client_credentials.sep)
for the complete template. Its token and API hosts must each be explicitly
allowed with the CLI `--allow-network-host` capability.
