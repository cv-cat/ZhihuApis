"""Pure-Python implementation of the current Zhihu 3.0 web encryptor.

The round keys and S-box are exported from the checked-in ``static/other.js``
module 1514.  The browser bundle currently exposes these values unchanged;
when Zhihu rotates the bundle, refresh this file from a new Network/script
capture and update the known vector test.  No browser, Playwright, Node, or
JS VM is used at runtime.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Callable

# module 1514 h.zk/h.zb from the bundle used by ZhihuApis.  Values are signed
# JavaScript int32 values; the SM4 implementation masks each operation.
ROUND_KEYS = [1170614578, 1024848638, 1413669199, -343334464, -766094290, -1373058082, -143119608, -297228157, 1933479194, -971186181, -406453910, 460404854, -547427574, -1891326262, -1679095901, 2119585428, -2029270069, 2035090028, -1521520070, -5587175, -77751101, -2094365853, -1243052806, 1579901135, 1321810770, 456816404, -1391643889, -229302305, 330002838, -788960546, 363569021, -1947871109]
SBOX = [20, 223, 245, 7, 248, 2, 194, 209, 87, 6, 227, 253, 240, 128, 222, 91, 237, 9, 125, 157, 230, 93, 252, 205, 90, 79, 144, 199, 159, 197, 186, 167, 39, 37, 156, 198, 38, 42, 43, 168, 217, 153, 15, 103, 80, 189, 71, 191, 97, 84, 247, 95, 36, 69, 14, 35, 12, 171, 28, 114, 178, 148, 86, 182, 32, 83, 158, 109, 22, 255, 94, 238, 151, 85, 77, 124, 254, 18, 4, 26, 123, 176, 232, 193, 131, 172, 143, 142, 150, 30, 10, 146, 162, 62, 224, 218, 196, 229, 1, 192, 213, 27, 110, 56, 231, 180, 138, 107, 242, 187, 54, 120, 19, 44, 117, 228, 215, 203, 53, 239, 251, 127, 81, 11, 133, 96, 204, 132, 41, 115, 73, 55, 249, 147, 102, 48, 122, 145, 106, 118, 74, 190, 29, 16, 174, 5, 177, 129, 63, 113, 99, 31, 161, 76, 246, 34, 211, 13, 60, 68, 207, 160, 65, 111, 82, 165, 67, 169, 225, 57, 112, 244, 155, 51, 236, 200, 233, 58, 61, 47, 100, 137, 185, 64, 17, 70, 234, 163, 219, 108, 170, 166, 59, 149, 52, 105, 24, 212, 78, 173, 45, 0, 116, 226, 119, 136, 206, 135, 175, 195, 25, 92, 121, 208, 126, 139, 3, 75, 141, 21, 130, 98, 241, 40, 154, 66, 184, 49, 181, 46, 243, 88, 101, 183, 8, 23, 72, 188, 104, 179, 210, 134, 250, 201, 164, 89, 216, 202, 220, 50, 221, 152, 140, 33, 235, 214]

_CUSTOM_ALPHABET = "6fpLRqJO8M/c3jnYxFkUVC4ZIG12SiH=5v0mXDazWBTsuw7QetbKdoPyAl+hN9rgE"
_STANDARD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
# The extra '=' in the browser table is intentional.  The 48-byte payload
# has no padding, so only indices 0..63 are selected.
_CUSTOM_TRANS = str.maketrans(_STANDARD_ALPHABET, _CUSTOM_ALPHABET[:64])
_CONST = bytes([232, 0, 0, 2, 128, 192, 0, 8, 14, 0, 0, 0]) * 4
_MASK = 0xFFFFFFFF
_K = (0x13, 0x1A, 0x1F, 0x19, 0x4C, 0x1D, 0x4E, 0x1B, 0x1F, 0x4F, 0x1A, 0x1B, 0x4E, 0x1D)


def _rol32(value: int, shift: int) -> int:
    value &= _MASK
    return ((value << shift) | (value >> (32 - shift))) & _MASK


def _word(data: bytes | bytearray) -> int:
    return ((data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]) & _MASK


def _bytes(value: int) -> bytes:
    return bytes(((value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF))


def _sm4_round_transform(value: int) -> int:
    raw = _bytes(value)
    substituted = _word(bytes(SBOX[b] for b in raw))
    return substituted ^ _rol32(substituted, 2) ^ _rol32(substituted, 10) ^ _rol32(substituted, 18) ^ _rol32(substituted, 24)


def sm4_encrypt_block(block: bytes, round_keys: list[int] | tuple[int, ...] = ROUND_KEYS) -> bytes:
    """Encrypt one 16-byte block using the bundle's SM4 round keys."""

    if len(block) != 16:
        raise ValueError("SM4 block must contain exactly 16 bytes")
    if len(round_keys) != 32:
        raise ValueError("Zhihu round-key table must contain 32 words")
    state = [_word(block[offset : offset + 4]) for offset in range(0, 16, 4)]
    for index, key in enumerate(round_keys):
        state.append((state[index] ^ _sm4_round_transform(state[index + 1] ^ state[index + 2] ^ state[index + 3] ^ key)) & _MASK)
    return b"".join(_bytes(state[index]) for index in (35, 34, 33, 32))


def _random_byte(random_value: float | None = None) -> int:
    """Reproduce the browser's 0..126 random-byte bit permutation."""

    if random_value is None:
        # SystemRandom mirrors Math.random's non-deterministic request nonce.
        key = secrets.randbelow(127)
    else:
        if not 0 <= random_value < 1:
            raise ValueError("random_value must be in [0, 1)")
        key = int(random_value * 127)
    low = key & 0x1F
    permuted = ((~low & 0x18) | (low & 0x04) | ((low ^ 0x02) & 0x03)) & 0x1F
    return (key & ~0x1F) | permuted


def encrypt_md5_hex(md5_hex: str, *, random_value: float | None = None) -> str:
    """Return the 64-character body appended to ``2.0_`` in x-zse-96."""

    if len(md5_hex) != 32 or any(ch not in "0123456789abcdefABCDEF" for ch in md5_hex):
        raise ValueError("md5_hex must be a 32-character hexadecimal digest")
    block = bytes((_random_byte(random_value), 0x14, *(ord(ch) ^ _K[index] for index, ch in enumerate(md5_hex[:14]))))
    iv = sm4_encrypt_block(block)
    plaintext = md5_hex[14:32].encode("ascii") + bytes([0x0E]) * 14
    cipher = bytearray()
    previous = iv
    for offset in range(0, len(plaintext), 16):
        mixed = bytes(left ^ right for left, right in zip(plaintext[offset : offset + 16], previous))
        previous = sm4_encrypt_block(mixed)
        cipher.extend(previous)
    mixed = bytes(cipher[::-1] + iv[::-1])
    encoded = bytearray()
    for offset in range(0, len(mixed), 3):
        b0, b1, b2 = mixed[offset : offset + 3]
        encoded.extend((
            ((b0 & 0x3F) << 2) | ((b1 >> 2) & 0x03),
            ((b1 & 0x03) << 6) | ((b0 >> 6) << 4) | ((b2 & 0x03) << 2) | (b1 >> 6),
            ((b1 & 0x30) << 2) | ((b2 >> 2) & 0x3F),
        ))
    payload = bytes(left ^ right for left, right in zip(encoded, _CONST))
    return base64.b64encode(payload).decode("ascii").translate(_CUSTOM_TRANS)


def encrypt_source(source: str, *, random_value: float | None = None) -> str:
    """Hash a browser source string and return the unversioned encrypted body."""

    return encrypt_md5_hex(hashlib.md5(source.encode("utf-8")).hexdigest(), random_value=random_value)


__all__ = ["ROUND_KEYS", "SBOX", "encrypt_md5_hex", "encrypt_source", "sm4_encrypt_block"]
