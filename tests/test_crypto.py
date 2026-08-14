import base64
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference"))

from separan.auth import SecretValue
from separan.builtins import BUILTINS
from separan.cli import execute
from separan.errors import SeparanError
from separan.interpreter import Interpreter
from separan.randomness import BytesValue
from separan.token import SourcePosition


class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Interpreter()
        self.position = SourcePosition("crypto.sep", 1, 1, "crypto")

    def call(self, name, *arguments):
        return BUILTINS[name].call(list(arguments), self.position, self.runtime)

    def assert_error(self, name, code, *arguments):
        with self.assertRaises(SeparanError) as caught:
            self.call(name, *arguments)
        self.assertEqual(caught.exception.code, code)

    def test_hashes_return_bytes_and_match_known_vectors(self):
        source = '''print bytes_to_hexadecimal(sha256_hash("abc"))
print bytes_to_hexadecimal(sha512_hash("abc"))
print bytes_to_hexadecimal(sha3_256_hash("abc"))
print bytes_to_hexadecimal(sha3_512_hash("abc"))
'''
        expected = "\n".join((
            hashlib.sha256(b"abc").hexdigest().upper(),
            hashlib.sha512(b"abc").hexdigest().upper(),
            hashlib.sha3_256(b"abc").hexdigest().upper(),
            hashlib.sha3_512(b"abc").hexdigest().upper(),
        )) + "\n"
        self.assertEqual(execute(source)[1], expected)

    def test_hmacs_and_readable_codec_aliases(self):
        source = '''a = sha256_hmac("key", "data")
b = sha512_hmac("key", "data")
print bytes_to_hexadecimal(a)
print bytes_to_hexadecimal(b)
print hexadecimal_to_bytes(bytes_to_hexadecimal(a)) == a
print base64_to_bytes(bytes_to_base64(b)) == b
'''
        import hmac
        expected = (
            hmac.new(b"key", b"data", hashlib.sha256).hexdigest().upper() + "\n" +
            hmac.new(b"key", b"data", hashlib.sha512).hexdigest().upper() + "\ntrue\ntrue\n"
        )
        self.assertEqual(execute(source)[1], expected)

    def test_constant_time_comparison_accepts_secret_boundary(self):
        self.assertTrue(self.call("constant_time_equal", SecretValue(b"token"), "token"))
        self.assertFalse(self.call("constant_time_equal", SecretValue(b"token"), "other"))
        self.assert_error("constant_time_equal", "E201", 1, 1)

    def test_argon2id_password_hash_and_legacy_scrypt_verification(self):
        generated = self.call("password_hash", "password")
        self.assertTrue(generated.startswith("$argon2id$"))
        self.assertTrue(self.call("password_verify", "password", generated))
        self.assertFalse(self.call("password_verify", "wrong", generated))

        salt = b"0123456789abcdef"
        digest = hashlib.scrypt(b"password", salt=salt, n=2**14, r=8, p=1, dklen=32)
        legacy = "$separan$scrypt$n=16384,r=8,p=1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()
        self.assertTrue(self.call("password_verify", "password", legacy))

    def test_key_derivation_is_deterministic_and_redacted(self):
        salt = BytesValue(b"0123456789abcdef")
        first = self.call("derive_key_from_password", "password", salt)
        second = self.call("derive_key_from_password", "password", salt)
        self.assertIsInstance(first, SecretValue)
        self.assertEqual(len(first.value), 32)
        self.assertEqual(first, second)
        self.assertEqual(execute('print derive_key_from_password("password", bytes_from_string("0123456789abcdef"))\n')[1], "[REDACTED]\n")
        self.assert_error("derive_key_from_password", "E923", "password", BytesValue(b"short"))

    def test_authenticated_encryption_round_trips_each_payload_type(self):
        key = BytesValue(b"K" * 32)
        for value, expected_type in (("日本語", str), (BytesValue(b"\x00\xff"), BytesValue), (SecretValue(b"hidden"), SecretValue)):
            with self.subTest(value=value):
                encrypted = self.call("encrypt_authenticated", key, value)
                self.assertIsInstance(encrypted, BytesValue)
                self.assertNotIn(value.value if hasattr(value, "value") else value.encode(), encrypted.value)
                restored = self.call("decrypt_authenticated", key, encrypted)
                self.assertIsInstance(restored, expected_type)
                self.assertEqual(restored, value)
        self.assertNotEqual(self.call("encrypt_authenticated", key, "same"), self.call("encrypt_authenticated", key, "same"))

    def test_authenticated_encryption_rejects_string_key_wrong_key_and_tamper(self):
        key = BytesValue(b"K" * 32)
        encrypted = self.call("encrypt_authenticated", key, "message")
        self.assert_error("encrypt_authenticated", "E201", "K" * 32, "message")
        self.assert_error("encrypt_authenticated", "E920", BytesValue(b"short"), "message")
        self.assert_error("decrypt_authenticated", "E922", BytesValue(b"W" * 32), encrypted)
        changed = bytearray(encrypted.value)
        changed[-1] ^= 1
        self.assert_error("decrypt_authenticated", "E922", key, BytesValue(bytes(changed)))
        self.assert_error("decrypt_authenticated", "E921", key, BytesValue(b"not a container"))

    def test_password_encryption_round_trip_and_authentication(self):
        encrypted = self.call("encrypt_with_password", "correct", SecretValue(b"api-key"))
        restored = self.call("decrypt_with_password", "correct", encrypted)
        self.assertEqual(restored, SecretValue(b"api-key"))
        self.assert_error("decrypt_with_password", "E922", "wrong", encrypted)

    def test_crypto_authentication_error_is_catchable(self):
        source = '''function:main
key = bytes_from_string("0123456789abcdef0123456789abcdef")
wrong = bytes_from_string("abcdef0123456789abcdef0123456789")
encrypted = encrypt_authenticated(key, "message")
try :decrypt
print decrypt_authenticated(wrong, encrypted)
catch crypto_error :decrypt
print "rejected"
endtry:decrypt
end_function:main
'''
        self.assertEqual(execute(source)[1], "rejected\n")

    def test_secure_random_number_is_inclusive_alias(self):
        self.assertEqual(execute("print secure_random_number(7, 7)\n")[1], "7\n")

    def test_obsolete_or_unauthenticated_algorithms_are_not_exposed(self):
        for name in ("md5_hash", "sha1_hash", "des_encrypt", "rc4_encrypt", "aes_ecb_encrypt"):
            with self.subTest(name=name):
                self.assertNotIn(name, BUILTINS)


if __name__ == "__main__":
    unittest.main()
