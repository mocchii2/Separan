"""Safe-purpose cryptography and explicit cryptographic primitives."""

import hashlib
import hmac
import os
import struct

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .auth import SecretValue, secret_bytes
from .errors import error
from .randomness import BytesValue
from .system_utilities import UtilityFunction


AEAD_MAGIC = b"SEPARAN-AEAD\0"
PASSWORD_AEAD_MAGIC = b"SEPARAN-PASSWORD-AEAD\0"
CONTAINER_VERSION = 1
TEXT_KIND, BYTES_KIND, SECRET_KIND = 1, 2, 3
NONCE_LENGTH = 12
SALT_LENGTH = 16
KEY_LENGTH = 32
TAG_LENGTH = 16
ARGON_MEMORY_KIB, ARGON_TIME, ARGON_LANES = 65_536, 3, 4
MAX_CRYPTO_BYTES = 67_108_864


def _compatible(value, name, position, runtime):
    return secret_bytes(value, name, position, runtime)


def _hash(name, constructor):
    def implementation(arguments, named, position, runtime):
        data = _compatible(arguments[0], f"{name}() data", position, runtime)
        return BytesValue(constructor(data).digest())
    return implementation


def _hmac(name, constructor):
    def implementation(arguments, named, position, runtime):
        key = _compatible(arguments[0], f"{name}() key", position, runtime)
        data = _compatible(arguments[1], f"{name}() data", position, runtime)
        return BytesValue(hmac.new(key, data, constructor).digest())
    return implementation


def _constant_time_equal(arguments, named, position, runtime):
    left = _compatible(arguments[0], "constant_time_equal() left", position, runtime)
    right = _compatible(arguments[1], "constant_time_equal() right", position, runtime)
    return hmac.compare_digest(left, right)


def _key(value, function, position, runtime):
    if not isinstance(value, (SecretValue, BytesValue)):
        runtime.type_error(position, "32-byte secret or bytes key", runtime.type_name(value), f"{function}() key must be secret or bytes; string keys are not accepted.")
    raw = value.value
    if len(raw) != KEY_LENGTH:
        raise error("E890", "crypto_error", f"{function}() requires an exact 32-byte AES-256 key.", position, expected="32 bytes", actual=f"{len(raw)} bytes")
    return raw


def _payload(value, function, position, runtime):
    if type(value) is str: return TEXT_KIND, value.encode("utf-8")
    if isinstance(value, BytesValue): return BYTES_KIND, value.value
    if isinstance(value, SecretValue): return SECRET_KIND, value.value
    runtime.type_error(position, "string, bytes, or secret", runtime.type_name(value), f"{function}() plaintext must be string, bytes, or secret.")


def _restore(kind, value, position):
    if kind == BYTES_KIND: return BytesValue(value)
    if kind == SECRET_KIND: return SecretValue(value)
    if kind == TEXT_KIND:
        try: return value.decode("utf-8")
        except UnicodeDecodeError: raise error("E891", "crypto_error", "Authenticated container contains invalid UTF-8 text.", position)
    raise error("E891", "crypto_error", "Authenticated container has an unsupported payload type.", position)


def _bounded(value, function, position):
    if len(value) > MAX_CRYPTO_BYTES:
        raise error("E890", "crypto_error", f"{function}() input exceeds the cryptographic size limit.", position, expected=f"at most {MAX_CRYPTO_BYTES} bytes", actual=f"{len(value)} bytes")


def _encrypt_authenticated(arguments, named, position, runtime):
    key = _key(arguments[0], "encrypt_authenticated", position, runtime)
    kind, plaintext = _payload(arguments[1], "encrypt_authenticated", position, runtime)
    _bounded(plaintext, "encrypt_authenticated", position)
    nonce = os.urandom(NONCE_LENGTH)
    header = AEAD_MAGIC + bytes((CONTAINER_VERSION, kind)) + nonce
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, header)
    return BytesValue(header + ciphertext)


def _decrypt_authenticated(arguments, named, position, runtime):
    key = _key(arguments[0], "decrypt_authenticated", position, runtime)
    container = arguments[1]
    if not isinstance(container, BytesValue):
        runtime.type_error(position, "bytes authenticated container", runtime.type_name(container), "decrypt_authenticated() encrypted value must be bytes.")
    raw = container.value
    minimum = len(AEAD_MAGIC) + 2 + NONCE_LENGTH + TAG_LENGTH
    if len(raw) < minimum or len(raw) > MAX_CRYPTO_BYTES + minimum or not raw.startswith(AEAD_MAGIC):
        raise error("E891", "crypto_error", "Authenticated container is malformed or too large.", position)
    offset = len(AEAD_MAGIC)
    version, kind = raw[offset:offset + 2]
    if version != CONTAINER_VERSION or kind not in (TEXT_KIND, BYTES_KIND, SECRET_KIND):
        raise error("E891", "crypto_error", "Authenticated container version or payload type is unsupported.", position)
    offset += 2
    nonce = raw[offset:offset + NONCE_LENGTH]
    offset += NONCE_LENGTH
    header, ciphertext = raw[:offset], raw[offset:]
    try: plaintext = AESGCM(key).decrypt(nonce, ciphertext, header)
    except InvalidTag: raise error("E892", "crypto_authentication_error", "Ciphertext was modified or the key is incorrect.", position)
    return _restore(kind, plaintext, position)


def _derive(password, salt):
    return hash_secret_raw(password, salt, ARGON_TIME, ARGON_MEMORY_KIB, ARGON_LANES, KEY_LENGTH, Type.ID)


def _derive_key_from_password(arguments, named, position, runtime):
    password = _compatible(arguments[0], "derive_key_from_password() password", position, runtime)
    salt = arguments[1]
    if not isinstance(salt, BytesValue):
        runtime.type_error(position, "bytes salt", runtime.type_name(salt), "derive_key_from_password() salt must be bytes.")
    if len(salt.value) < SALT_LENGTH or len(salt.value) > 1024:
        raise error("E893", "crypto_error", "Argon2id salt must contain between 16 and 1024 bytes.", position, expected="16..1024 bytes", actual=f"{len(salt.value)} bytes")
    return SecretValue(_derive(password, salt.value))


def _encrypt_with_password(arguments, named, position, runtime):
    password = _compatible(arguments[0], "encrypt_with_password() password", position, runtime)
    kind, plaintext = _payload(arguments[1], "encrypt_with_password", position, runtime)
    _bounded(plaintext, "encrypt_with_password", position)
    salt, nonce = os.urandom(SALT_LENGTH), os.urandom(NONCE_LENGTH)
    parameters = struct.pack(">IBB", ARGON_MEMORY_KIB, ARGON_TIME, ARGON_LANES)
    header = PASSWORD_AEAD_MAGIC + bytes((CONTAINER_VERSION, kind)) + parameters + salt + nonce
    ciphertext = AESGCM(_derive(password, salt)).encrypt(nonce, plaintext, header)
    return BytesValue(header + ciphertext)


def _decrypt_with_password(arguments, named, position, runtime):
    password = _compatible(arguments[0], "decrypt_with_password() password", position, runtime)
    container = arguments[1]
    if not isinstance(container, BytesValue):
        runtime.type_error(position, "bytes password container", runtime.type_name(container), "decrypt_with_password() encrypted value must be bytes.")
    raw = container.value
    fixed = len(PASSWORD_AEAD_MAGIC) + 2 + 6 + SALT_LENGTH + NONCE_LENGTH
    if len(raw) < fixed + TAG_LENGTH or len(raw) > MAX_CRYPTO_BYTES + fixed + TAG_LENGTH or not raw.startswith(PASSWORD_AEAD_MAGIC):
        raise error("E891", "crypto_error", "Password-encrypted container is malformed or too large.", position)
    offset = len(PASSWORD_AEAD_MAGIC)
    version, kind = raw[offset:offset + 2]
    offset += 2
    memory, time_cost, lanes = struct.unpack(">IBB", raw[offset:offset + 6])
    offset += 6
    if version != CONTAINER_VERSION or kind not in (TEXT_KIND, BYTES_KIND, SECRET_KIND) or (memory, time_cost, lanes) != (ARGON_MEMORY_KIB, ARGON_TIME, ARGON_LANES):
        raise error("E891", "crypto_error", "Password-encrypted container version or Argon2id parameters are unsupported.", position)
    salt = raw[offset:offset + SALT_LENGTH]
    offset += SALT_LENGTH
    nonce = raw[offset:offset + NONCE_LENGTH]
    offset += NONCE_LENGTH
    header, ciphertext = raw[:offset], raw[offset:]
    try: plaintext = AESGCM(_derive(password, salt)).decrypt(nonce, ciphertext, header)
    except InvalidTag: raise error("E892", "crypto_authentication_error", "Ciphertext was modified or the password is incorrect.", position)
    return _restore(kind, plaintext, position)


CRYPTO_BUILTINS = tuple(
    UtilityFunction(name, minimum, maximum, implementation)
    for name, minimum, maximum, implementation in (
        ("sha256_hash", 1, 1, _hash("sha256_hash", hashlib.sha256)),
        ("sha512_hash", 1, 1, _hash("sha512_hash", hashlib.sha512)),
        ("sha3_256_hash", 1, 1, _hash("sha3_256_hash", hashlib.sha3_256)),
        ("sha3_512_hash", 1, 1, _hash("sha3_512_hash", hashlib.sha3_512)),
        ("sha256_hmac", 2, 2, _hmac("sha256_hmac", hashlib.sha256)),
        ("sha512_hmac", 2, 2, _hmac("sha512_hmac", hashlib.sha512)),
        ("constant_time_equal", 2, 2, _constant_time_equal),
        ("derive_key_from_password", 2, 2, _derive_key_from_password),
        ("encrypt_authenticated", 2, 2, _encrypt_authenticated),
        ("decrypt_authenticated", 2, 2, _decrypt_authenticated),
        ("encrypt_with_password", 2, 2, _encrypt_with_password),
        ("decrypt_with_password", 2, 2, _decrypt_with_password),
    )
)
