"""Separated deterministic and cryptographic randomness for Separan."""

from dataclasses import dataclass
import math
import secrets

from .errors import error


MASK_64 = 2**64 - 1
MASK_32 = 2**32 - 1
MAX_SECURE_LENGTH = 1_048_576
SECURE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"


@dataclass(frozen=True)
class BytesValue:
    value: bytes


class SeparanRandom:
    """PCG-XSH-RR 32 with a language-defined seed and output procedure."""

    def __init__(self, seed=None):
        self.seed(secrets.randbits(64) if seed is None else seed)

    def seed(self, seed):
        self.state = 0
        self.increment = (54 << 1) | 1
        self.next_u32()
        self.state = (self.state + (seed & MASK_64)) & MASK_64
        self.next_u32()

    def next_u32(self):
        old = self.state
        self.state = (old * 6364136223846793005 + self.increment) & MASK_64
        shifted = (((old >> 18) ^ old) >> 27) & MASK_32
        rotation = old >> 59
        return ((shifted >> rotation) | (shifted << ((-rotation) & 31))) & MASK_32

    def bits(self, count):
        result, produced = 0, 0
        while produced < count:
            take = min(32, count - produced)
            result = (result << take) | (self.next_u32() >> (32 - take))
            produced += take
        return result

    def number(self):
        return ((self.next_u32() >> 5) * 67_108_864 + (self.next_u32() >> 6)) / 9_007_199_254_740_992

    def below(self, upper):
        if upper <= 0:
            raise ValueError("upper must be positive")
        bits = (upper - 1).bit_length()
        while True:
            candidate = self.bits(bits)
            if candidate < upper:
                return candidate

    def integer(self, minimum, maximum):
        return minimum + self.below(maximum - minimum + 1)

    def floating(self, minimum, maximum):
        value = minimum + (maximum - minimum) * self.number()
        return math.nextafter(maximum, minimum) if value >= maximum else value

    def shuffled(self, values):
        result = list(values)
        for index in range(len(result) - 1, 0, -1):
            other = self.below(index + 1)
            result[index], result[other] = result[other], result[index]
        return result

    def sample(self, values, count):
        result = list(values)
        for index in range(count):
            other = index + self.below(len(result) - index)
            result[index], result[other] = result[other], result[index]
        return result[:count]


def require_integer(value, function, position, runtime):
    if type(value) is not int:
        runtime.type_error(position, "integer number", runtime.type_name(value), f"{function}() requires integer-valued numbers.")


def require_number(value, function, position, runtime):
    if not runtime.is_number(value):
        runtime.type_error(position, "number", runtime.type_name(value), f"{function}() requires numbers.")


def require_list(value, function, position, runtime):
    if type(value) is not list:
        runtime.type_error(position, "list", runtime.type_name(value), f"{function}() requires a list.")


def secure_length(value, function, position, runtime):
    require_integer(value, function, position, runtime)
    if value < 0 or value > MAX_SECURE_LENGTH:
        raise error("E504", "Invalid secure random length", f"{function}() length must be between 0 and {MAX_SECURE_LENGTH}.", position, expected=f"0..{MAX_SECURE_LENGTH}", actual=str(value))


def secure_bytes(length): return BytesValue(secrets.token_bytes(length))
def secure_integer(minimum, maximum): return minimum + secrets.randbelow(maximum - minimum + 1)
def secure_string(length): return "".join(secrets.choice(SECURE_ALPHABET) for _ in range(length))
