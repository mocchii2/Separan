"""Versioned AES-256-GCM persistence for CookieJarValue."""

import json
import os
import struct

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .auth import SecretValue, secret_bytes
from .cookies import CookieJarValue, CookieRecord, _jar
from .errors import error
from .system_utilities import UtilityFunction


MAGIC = b"SEPARAN-COOKIE-STORE\0"
VERSION = 1
OS_MODE, PASSWORD_MODE, EXTERNAL_MODE = 1, 2, 3
ARGON_MEMORY_KIB, ARGON_TIME, ARGON_LANES = 65_536, 3, 4
MAX_STORE_BYTES = 16_777_216


def _serialize(jar):
    rows = []
    for item in jar.cookies:
        rows.append({"name": item.name, "value": item.value.decode("ascii"), "domain": item.domain, "path": item.path,
                     "expires": item.expires, "secure": item.secure, "http_only": item.http_only,
                     "same_site": item.same_site, "host_only": item.host_only, "order": item.order})
    return json.dumps({"cookies": rows, "counter": jar.counter}, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _deserialize(value, position):
    try:
        data = json.loads(value); rows, counter = data["cookies"], data["counter"]
        if type(rows) is not list or type(counter) is not int or counter < 0: raise ValueError
        jar = CookieJarValue(counter=counter)
        for row in rows:
            expected = {"name", "value", "domain", "path", "expires", "secure", "http_only", "same_site", "host_only", "order"}
            if type(row) is not dict or set(row) != expected: raise ValueError
            jar.cookies.append(CookieRecord(row["name"], row["value"].encode("ascii"), row["domain"], row["path"], row["expires"], row["secure"], row["http_only"], row["same_site"], row["host_only"], row["order"]))
        return jar
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError): raise error("E884", "Invalid cookie store", "Decrypted Cookie Store payload is invalid.", position)


def _mode(named, position, runtime, create):
    key, password = named.get("key"), named.get("password")
    if key is not None and password is not None: raise error("E882", "Ambiguous cookie protection", "Specify key or password, never both.", position)
    if password is not None:
        return PASSWORD_MODE, secret_bytes(password, "cookie password", position, runtime), os.urandom(16) if create else None
    if key is not None:
        raw = secret_bytes(key, "cookie key", position, runtime)
        if len(raw) != 32: raise error("E882", "Invalid cookie key", "External Cookie Store key must be exactly 32 bytes.", position, actual=str(len(raw)))
        return EXTERNAL_MODE, raw, b""
    if runtime.cookie_key_provider is None: raise error("E883", "Cookie key unavailable", "No OS-bound Cookie Store key provider is configured.", position)
    return OS_MODE, None, b""


def _derive(mode, material, salt, position, runtime, create):
    if mode == PASSWORD_MODE:
        return hash_secret_raw(material, salt, ARGON_TIME, ARGON_MEMORY_KIB, ARGON_LANES, 32, Type.ID)
    if mode == EXTERNAL_MODE: return material
    try: key = runtime.cookie_key_provider("separan-cookie-store-v1", create)
    except Exception as exc: raise error("E883", "Cookie key unavailable", str(exc), position)
    if type(key) is not bytes or len(key) != 32: raise error("E883", "Invalid OS cookie key", "OS-bound provider must return exactly 32 bytes.", position)
    return key


def _save(arguments, named, position, runtime):
    jar = _jar(arguments[0], "cookie_save_secure", position, runtime); path = runtime.capabilities.path(arguments[1], "cookie_save_secure", position)
    runtime.capabilities.require(runtime.capabilities.write_files, "write secure Cookie Store", position)
    mode, material, salt = _mode(named, position, runtime, True); key = _derive(mode, material, salt, position, runtime, True); nonce = os.urandom(12)
    header = MAGIC + bytes((VERSION, mode, len(salt))) + salt + nonce
    ciphertext = AESGCM(key).encrypt(nonce, _serialize(jar), header)
    from .io_json import _atomic_write
    _atomic_write(path, header + ciphertext, position); return None


def _load(arguments, named, position, runtime):
    path = runtime.capabilities.path(arguments[0], "cookie_load_secure", position); runtime.capabilities.require(runtime.capabilities.read_files, "read secure Cookie Store", position)
    try: container = path.read_bytes()
    except OSError as exc: raise error("E884", "Cookie Store I/O error", str(exc), position, actual=arguments[0])
    if len(container) > MAX_STORE_BYTES or not container.startswith(MAGIC) or len(container) < len(MAGIC) + 3 + 12 + 16: raise error("E884", "Invalid cookie store", "Cookie Store container is malformed or too large.", position)
    offset = len(MAGIC); version, mode, salt_length = container[offset:offset+3]; offset += 3
    if version != VERSION or mode not in (OS_MODE, PASSWORD_MODE, EXTERNAL_MODE) or salt_length not in (0, 16): raise error("E884", "Unsupported cookie store", "Cookie Store version or protection mode is unsupported.", position)
    salt = container[offset:offset+salt_length]; offset += salt_length; nonce = container[offset:offset+12]; offset += 12; header, ciphertext = container[:offset], container[offset:]
    requested_mode, material, _ = _mode(named, position, runtime, False)
    if requested_mode != mode: raise error("E882", "Cookie protection mismatch", "Load protection mode does not match the stored container.", position)
    try: plaintext = AESGCM(_derive(mode, material, salt, position, runtime, False)).decrypt(nonce, ciphertext, header)
    except InvalidTag: raise error("E885", "Cookie Store authentication failed", "Cookie Store was modified or the key/password is incorrect.", position)
    return _deserialize(plaintext, position)


COOKIE_STORE_BUILTINS = (
    UtilityFunction("cookie_save_secure", 2, 2, _save, ("key", "password")),
    UtilityFunction("cookie_load_secure", 1, 1, _load, ("key", "password")),
)
