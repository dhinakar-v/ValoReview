"""
Undo the seeded obfuscation Riot applies to replicator bunch payloads.

The bunch framing, the content block header and the payload's own bit count are
plaintext -- which is why this decoder reaches the content block and then reads
nothing useful.  The bits *inside* the payload are whitened by a keystream
seeded from `payload_bits ^ actor_net_guid`.  A correct UE property reader
pointed at those bytes decodes garbage, so the long-standing 0/151 result was
never a wrong handle encoding: it was the right reader on the wrong bytes.
Reverse this first and the interior is ordinary UE backwards-compatible rep
layout.

The constants rotate every Valorant patch, and the mixing differs structurally
between builds -- 12.10 uses adjacent-bit swaps and no substitution table at
all, 13.02 uses full bit reversal plus three of them -- so nothing here can be
extrapolated to an unregistered build.  An unknown branch therefore raises.  A
silent fallback to the nearest version would make a porting bug and a version
mismatch look identical, which is the one failure this module must not have.

Ported from ValorantReplayParser (MIT, Copyright (c) 2026 Michel Giehl):
  src/Replay.Encoding/PayloadEncryption/ValorantSeededTransformHelpers.cs
  src/Replay.Encoding/PayloadEncryption/VersionedTransforms/ValorantSeededTransform*.cs
See THIRD_PARTY.md.  C# integer arithmetic wraps at the declared width and
Python's does not, so every operation below masks explicitly; the masks are not
decoration and removing one produces subtly wrong output rather than an error.
"""

from __future__ import annotations

U64 = 0xFFFFFFFFFFFFFFFF
U32 = 0xFFFFFFFF
U8 = 0xFF

MULTIPLIER = 0x2545F4914F6CDD1D

# A block is only transformed when it is wholly present, so each loop runs
# while strictly more than (width - 1) bits remain.  The leftover then falls
# through to the next-smaller block, and finally to the tail XOR.
BLOCK64_MIN = 63
BLOCK32_MIN = 31
BLOCK8_MIN = 7

# Riot's three substitution tables.  Each is a permutation of 0..255, which the
# test module asserts: a truncated table is still valid hex and would otherwise
# fail silently, far away from here.
SUBSTITUTE_TABLE_32 = bytes.fromhex(
    "2167b396313fbad3d5062b16f1b651a79c7b419584251536a4703546b05fa6c3"
    "bb8638f62ea2a994831b6239f3d228149e9af2c9decc26a1d8d0748d69127189"
    "f758cd4db7114809b968c77cf42042f56b54756da81d6a07d7c50ea066db"
    "f899ad1004ff8fb1ef986c29e201183d371e654b4a6e24d9bd90fe135693"
    "34aa8b0d79e74992f98eca43cbc6da022d8c0fb2c08a4785aee0d477c40b"
    "5c617e335745e62ffd6f915b9fcf3c4fe33aede480087372ea63fbfcb8"
    "7a23a51f815952875dfa78c1b5beb4a3641c3253f07fdc3b7640ec309755"
    "4c00bc880c05e1df197d22c25a9be52a50bf1ac8035e2cd1abdd44ee82"
    "ce27afebd64e0ae9173e9de8ac60",
)
SUBSTITUTE_TABLE_64 = bytes.fromhex(
    "77b9042feb7d27c944739a3f36f565ddf7e0302da9985dde69a394a05e170678"
    "a4f6ab0343c828e56a8e1cf270cf5305d30dffa7a23a32255a1f48c1"
    "b7e16e85996047bbe48acbc01bea6164f0c2d88bcdfdadb819b5bf0e9181"
    "839d45d249e9c731bd20bec66680d179d7e6fca15b5fdff1d0506752fe"
    "7b3513f846b3758de33e2ef4dc342a0823e20c094beec30f248f544c"
    "5539cc1d1e3b2272da296b41aaa6122c93ca9c970a56a87a9eb462923"
    "d9f38f3408437b2d4af7633fa21effb716f9082511ac574f95907ba11"
    "b1acd6ede702ae9610167c4f881426bc1501684a2b0b7fa54ee86dec4d"
    "b05cc4009558b6d57e42db5718866cced99b89873c8c63",
)
SUBSTITUTE_TABLE_8 = bytes.fromhex(
    "0a6c6996cadc5a08b38339a0f9adf4560e6e4c85649982d4885c8736239a"
    "112db8c4341866136f59e07422faa665e2d7954e94b0779e1aeee705a"
    "2c830900d9bd219c93a471512a9291f53acaf4352aef54dbfbee34a06"
    "d5d0a378a7d61c7a6b81d8dee568fb267ebcbae8cce4727f2cfcf0"
    "ec28716048ef3e038f1ef16a8df2461b9c86f7b476628a10fd6d0b"
    "3f9f2f555fc3c6921627d344840fe1808cb7738945db332550ea0414"
    "c50c32415e79a41d3d5b4037c1cffe2b54eb9d4991f307173cda57"
    "8bcd61f6ce702eff2193972a7d67abb57c5d0042a5d92051eddd0209"
    "c2d1f8bdbbe93524985838aab9a8b27501cbc063df3b8ec731b1a1"
    "b6e67b4b4f",
)


class UnsupportedBuildError(Exception):
    """No transform is registered for this replay's build branch."""


# --- bit primitives ------------------------------------------------------


def _rotl64(value: int, count: int) -> int:
    return ((value << count) | (value >> (64 - count))) & U64


def _rotr64(value: int, count: int) -> int:
    return ((value >> count) | (value << (64 - count))) & U64


def _rotl32(value: int, count: int) -> int:
    return ((value << count) | (value >> (32 - count))) & U32


def _rotr32(value: int, count: int) -> int:
    return ((value >> count) | (value << (32 - count))) & U32


def _rotl8(value: int, count: int) -> int:
    return ((value << count) | (value >> (8 - count))) & U8


def _rotr8(value: int, count: int) -> int:
    return ((value >> count) | (value << (8 - count))) & U8


def _swap64(value: int) -> int:
    return (
        ((value & 0x5555555555555555) << 1) | ((value >> 1) & 0x5555555555555555)
    ) & U64


def _swap32(value: int) -> int:
    return (((value & 0x55555555) << 1) | ((value >> 1) & 0x55555555)) & U32


def _swap8(value: int) -> int:
    return (((value & 0x55) << 1) | ((value >> 1) & 0x55)) & U8


def _reverse64(value: int) -> int:
    """UE-style 64-bit reversal that deliberately omits the final 16-bit swap."""
    value = ((value & 0x5555555555555555) << 1) | ((value >> 1) & 0x5555555555555555)
    value = ((value & 0x3333333333333333) << 2) | ((value >> 2) & 0x3333333333333333)
    value = ((value & 0x0F0F0F0F0F0F0F0F) << 4) | ((value >> 4) & 0x0F0F0F0F0F0F0F0F)
    value = ((value & 0x00FF00FF00FF00FF) << 8) | ((value >> 8) & 0x00FF00FF00FF00FF)
    return ((value << 32) | (value >> 32)) & U64


def _reverse32(value: int) -> int:
    value = ((value & 0x55555555) << 1) | ((value >> 1) & 0x55555555)
    value = ((value & 0x33333333) << 2) | ((value >> 2) & 0x33333333)
    value = ((value & 0x0F0F0F0F) << 4) | ((value >> 4) & 0x0F0F0F0F)
    value = ((value & 0x00FF00FF) << 8) | ((value >> 8) & 0x00FF00FF)
    return ((value << 16) | (value >> 16)) & U32


def _reverse8(value: int) -> int:
    value = ((value & 0x55) << 1) | ((value >> 1) & 0x55)
    value = ((value & 0x33) << 2) | ((value >> 2) & 0x33)
    return (((value & 0x0F) << 4) | ((value >> 4) & 0x0F)) & U8


def _sub64(value: int, table: bytes) -> int:
    return int.from_bytes(
        bytes(table[b] for b in value.to_bytes(8, "little")),
        "little",
    )


def _sub32(value: int, table: bytes) -> int:
    return int.from_bytes(
        bytes(table[b] for b in value.to_bytes(4, "little")),
        "little",
    )


# --- keystream -----------------------------------------------------------


def _initial_prng_b(seed: int) -> int:
    seed &= U32
    mixed = ((((seed >> 15) ^ seed) >> 12) ^ ((seed << 25) & U32) ^ seed) & U32
    return (mixed * MULTIPLIER) & U64


def _advance(state: int, prng_a: int, prng_b: int) -> tuple[int, int, int, int]:
    total = (prng_b + prng_a) & U64
    prng_b ^= prng_a
    prng_a = (_rotr64(prng_a, 9) ^ ((prng_b << 14) & U64) ^ prng_b) & U64
    prng_b = _rotl64(prng_b, 36)
    state = (total >> 32) & U32
    return state, prng_a, prng_b, state & U8


# --- transforms ----------------------------------------------------------


class _Transform:
    """
    One build's payload transform, in the direction a reader needs.

    It is not an involution -- applying it twice does not return the
    original bytes -- so there is no encode path here and none is needed:
    replays are only ever read.
    """

    branch = ""
    seed_addend = 0
    init_a_offset = 0
    init_a_adds = False
    tail_xor = 0

    def _initial_prng_a(self, seed: int) -> int:
        seed &= U32
        seed_plus = (seed + self.seed_addend) & U32
        offset = (
            seed + self.init_a_offset if self.init_a_adds else seed - self.init_a_offset
        )
        mixed = (
            (((seed_plus >> 15) ^ seed_plus) >> 12)
            ^ (((offset & U32) * 0x02000000) & U32)
            ^ seed_plus
        ) & U32
        return (mixed * MULTIPLIER) & U64

    def _u64(self, value: int, state: int) -> int:
        raise NotImplementedError

    def _u32(self, value: int, state: int) -> int:
        raise NotImplementedError

    def _u8(self, value: int, state: int) -> int:
        raise NotImplementedError

    def apply(self, payload: bytes, bit_count: int, seed: int) -> bytes:
        """
        Transform `bit_count` bits of `payload` under `seed`.

        Bits past `bit_count` in the final byte are cleared first, matching the
        zero-initialised buffer the reference implementation copies into.  They
        would otherwise leak into the tail XOR and corrupt the last byte.
        """
        if bit_count < 0:
            msg = f"bit count cannot be negative: {bit_count}"
            raise ValueError(msg)
        byte_count = (bit_count + 7) // 8
        if len(payload) < byte_count:
            msg = f"payload holds {len(payload)} bytes, need {byte_count}"
            raise ValueError(msg)
        if bit_count == 0:
            return b""

        data = bytearray(payload[:byte_count])
        spare = (8 - (bit_count & 7)) & 7
        if spare:
            data[-1] &= U8 >> spare

        state = seed & U32
        stream_byte = seed & U8
        prng_a = self._initial_prng_a(seed)
        prng_b = _initial_prng_b(seed)
        offset = 0
        remaining = bit_count

        while remaining > BLOCK64_MIN:
            value = self._u64(
                int.from_bytes(data[offset : offset + 8], "little"),
                state,
            )
            data[offset : offset + 8] = value.to_bytes(8, "little")
            state, prng_a, prng_b, stream_byte = _advance(state, prng_a, prng_b)
            offset += 8
            remaining -= 64

        while remaining > BLOCK32_MIN:
            value = self._u32(
                int.from_bytes(data[offset : offset + 4], "little"),
                state,
            )
            data[offset : offset + 4] = value.to_bytes(4, "little")
            state, prng_a, prng_b, stream_byte = _advance(state, prng_a, prng_b)
            offset += 4
            remaining -= 32

        while remaining > BLOCK8_MIN:
            data[offset] = self._u8(data[offset], state)
            state, prng_a, prng_b, stream_byte = _advance(state, prng_a, prng_b)
            offset += 1
            remaining -= 8

        if remaining:
            mask = U8 >> (7 - ((bit_count - 1) & 7))
            data[offset] ^= mask & (stream_byte ^ self.tail_xor)

        return bytes(data)


class Transform1210(_Transform):
    branch = "++Ares-Core+release-12.10"
    seed_addend = 0x12FD0EE5
    init_a_offset = 0x1B
    init_a_adds = False
    tail_xor = 0xE5

    def _u64(self, value: int, state: int) -> int:
        ror4 = _rotr32(state, 4)
        ror5 = _rotr32(state, 5)
        ror6 = _rotr32(state, 6)
        ror8 = _rotr32(state, 8)
        value = _rotr64(value, (ror8 % 63) + 1)
        value = _swap64(value)
        value = (value - ror6) & U64
        value = _rotr64(value, (ror5 % 63) + 1)
        return _swap64(value ^ ((~ror4) & U64))

    def _u32(self, value: int, state: int) -> int:
        rol4 = _rotl32(state, 4)
        rol5 = _rotl32(state, 5)
        rol6 = _rotl32(state, 6)
        rol8 = _rotl32(state, 8)
        value = _rotr32(value, (rol8 % 31) + 1)
        value = _swap32(value)
        value = (value - rol6) & U32
        value = _rotr32(value, (rol5 % 31) + 1)
        return _swap32(value ^ rol4)

    def _u8(self, value: int, state: int) -> int:
        addend1 = (state * 0x31) & U8
        addend2 = (state * 0x29) & U8
        value = _rotr8(value, (((state * 0x0CC6DB61) & U32) % 7) + 1)
        value = _swap8(value)
        value = (value - addend2) & U8
        value = _rotr8(value, (((state * 0x2751B) & U32) % 7) + 1)
        return _swap8(value ^ addend1)


class Transform1211(_Transform):
    branch = "++Ares-Core+release-12.11"
    seed_addend = 0x409D36A3
    init_a_offset = 0x23
    init_a_adds = True
    tail_xor = 0xA3

    def _u64(self, value: int, state: int) -> int:
        ror2 = _rotr32(state, 2)
        ror3 = _rotr32(state, 3)
        ror4 = _rotr32(state, 4)
        ror6 = _rotr32(state, 6)
        ror8 = _rotr32(state, 8)
        value = _rotr64(value, (ror8 % 63) + 1)
        value = _swap64(value)
        value = (value + ror6) & U64
        value = _reverse64(value)
        value = (value - ror4) & U64
        value = (value - ror3) & U64
        value = (value - ror2) & U64
        return _swap64(value)

    def _u32(self, value: int, state: int) -> int:
        rol2 = _rotl32(state, 2)
        rol3 = _rotl32(state, 3)
        rol4 = _rotl32(state, 4)
        rol6 = _rotl32(state, 6)
        rol8 = _rotl32(state, 8)
        value = _rotr32(value, (rol8 % 31) + 1)
        value = _swap32(value)
        value = (value + rol6) & U32
        value = _reverse32(value)
        value = (value - rol4) & U32
        value = (value - rol3) & U32
        value = (value - rol2) & U32
        return _swap32(value)

    def _u8(self, value: int, state: int) -> int:
        state_byte = state & U8
        value = _rotr8(value, (((state * 0x0CC6DB61) & U32) % 7) + 1)
        value = _swap8(value)
        value = (value + ((state_byte * 0x29) & U8)) & U8
        value = _reverse8(value)
        value = (value + ((state_byte * 0x23) & U8)) & U8
        return _swap8(value)


class Transform1300(_Transform):
    branch = "++Ares-Core+release-13.00"
    seed_addend = 0x2949B6EF
    init_a_offset = 0x11
    init_a_adds = False
    tail_xor = 0xEF

    def _u64(self, value: int, state: int) -> int:
        ror1 = _rotr32(state, 1)
        ror3 = _rotr32(state, 3)
        ror6 = _rotr32(state, 6)
        ror8 = _rotr32(state, 8)
        value = (value + ror8) & U64
        value = _reverse64(value)
        value = ((value + ror6) & U64) ^ ror3
        value = _sub64(value, SUBSTITUTE_TABLE_64)
        return _rotr64(value, (ror1 % 63) + 1)

    def _u32(self, value: int, state: int) -> int:
        rol1 = _rotl32(state, 1)
        rol3 = _rotl32(state, 3)
        rol6 = _rotl32(state, 6)
        rol8 = _rotl32(state, 8)
        value = (value + rol8) & U32
        value = _reverse32(value)
        value = ((~((value + rol6) & U32)) & U32) ^ rol3
        value = _sub32(value, SUBSTITUTE_TABLE_32)
        return _rotr32(value, (rol1 % 31) + 1)

    def _u8(self, value: int, state: int) -> int:
        mix = (state * 0x533) & U32
        mix_byte = mix & U8
        value = (value + mix_byte * 0x1B) & U8
        value = _reverse8(value)
        value = (~(value + mix_byte * 0x33) ^ mix_byte) & U8
        value = SUBSTITUTE_TABLE_8[value]
        return _rotr8(value, (((state * 0x0B) & U32) % 7) + 1)


class Transform1301(_Transform):
    branch = "++Ares-Core+release-13.01"
    seed_addend = 0xE62FCD5C
    init_a_offset = 0x24
    init_a_adds = False
    tail_xor = 0x5C

    def _u64(self, value: int, state: int) -> int:
        value = _swap64((~value) & U64) ^ ((~_rotr32(state, 5)) & U64)
        value = (~_rotr64(value, (_rotr32(state, 4) % 63) + 1)) & U64
        return (value + _rotr32(state, 1)) & U64

    def _u32(self, value: int, state: int) -> int:
        value = _swap32((~value) & U32) ^ _rotl32(state, 5)
        value = (~_rotr32(value, (_rotl32(state, 4) % 31) + 1)) & U32
        return (value + _rotl32(state, 1)) & U32

    def _u8(self, value: int, state: int) -> int:
        state11 = (state * 0x0B) & U32
        mix = (state11 * 0x533) & U32
        value = (_swap8((~value) & U8) ^ ((mix * 0x0B) & U8)) & U8
        value = (~_rotr8(value, (mix % 7) + 1)) & U8
        return (value + (state11 & U8)) & U8


class Transform1302(_Transform):
    branch = "++Ares-Core+release-13.02"
    seed_addend = 0x9E81A37C
    init_a_offset = 0x04
    init_a_adds = False
    tail_xor = 0x7C

    def _u64(self, value: int, state: int) -> int:
        value = _sub64(value, SUBSTITUTE_TABLE_64)
        ror2 = _rotr32(state, 2)
        ror3 = _rotr32(state, 3)
        ror6 = _rotr32(state, 6)
        value = _reverse64(value)
        value = (~((value - ror6) & U64)) & U64
        value = _reverse64(value)
        value = _rotl64(value, (ror3 % 63) + 1)
        return _rotr64(value, (ror2 % 63) + 1)

    def _u32(self, value: int, state: int) -> int:
        value = _sub32(value, SUBSTITUTE_TABLE_32)
        rol2 = _rotl32(state, 2)
        rol3 = _rotl32(state, 3)
        rol6 = _rotl32(state, 6)
        value = _reverse32(value)
        value = (~((value - rol6) & U32)) & U32
        value = _reverse32(value)
        value = _rotl32(value, (rol3 % 31) + 1)
        return _rotr32(value, (rol2 % 31) + 1)

    def _u8(self, value: int, state: int) -> int:
        mix_a = (state * 0x79) & U32
        mix_b = (mix_a * 0x0B) & U32
        value = SUBSTITUTE_TABLE_8[value]
        value = _reverse8(value)
        value = (~(value - ((mix_b * 0x33) & U8))) & U8
        value = _reverse8(value)
        value = _rotl8(value, (mix_b % 7) + 1)
        return _rotr8(value, (mix_a % 7) + 1)


TRANSFORMS: dict[str, _Transform] = {
    t.branch: t
    for t in (
        Transform1210(),
        Transform1211(),
        Transform1300(),
        Transform1301(),
        Transform1302(),
    )
}

SUPPORTED_BRANCHES = tuple(sorted(TRANSFORMS))


def seed_for(bit_count: int, actor_net_guid: int) -> int:
    """The per-payload keystream seed.  Riot's derivation, not a choice of ours."""
    return (bit_count & U32) ^ (actor_net_guid & U32)


def transform_for(branch: str) -> _Transform:
    """
    The transform for a build branch, or raise.

    Deliberately an exact match with no nearest-version fallback: the mixing
    differs structurally between builds, so a fallback would silently produce
    plausible-looking rubbish instead of an error, and a porting bug would be
    indistinguishable from a version mismatch.
    """
    try:
        return TRANSFORMS[branch]
    except KeyError:
        supported = ", ".join(SUPPORTED_BRANCHES)
        msg = f"no payload transform for build {branch!r}; supported: {supported}"
        raise UnsupportedBuildError(msg) from None


def decode(payload: bytes, bit_count: int, actor_net_guid: int, branch: str) -> bytes:
    """Deobfuscate one content block payload.  The result is plain UE bits."""
    return transform_for(branch).apply(
        payload,
        bit_count,
        seed_for(bit_count, actor_net_guid),
    )
