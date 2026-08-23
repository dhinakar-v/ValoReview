"""
Known-answer tests for the Valorant payload transform.

These vectors are the reference implementation's own, ported verbatim from
ValorantReplayParser's `ValorantSeededTransformTests.cs` (MIT, Copyright (c)
2026 Michel Giehl).  Keeping them byte-for-byte is the point: the transform has
no redundancy and no self-check, so one wrong rotation or one dropped mask still
yields output of the right length that still looks random.  Only a known answer
catches that.

The bit lengths are not arbitrary.  0/1/7 exercise the ragged tail with no block
loop at all; 8/31/32/63/64/65 straddle every 8-, 32- and 64-bit block boundary,
where an off-by-one in the loop conditions hides; 287 and 288 exercise a full
multi-block payload with and without a tail.  A port that passes 287 but fails 8
has its block handling wrong -- which is exactly how the first draft of this
module failed, on 12.11 alone, by dropping a trailing bit swap.

`test_handle_chain_terminates_on_zero_bits_left` is the one that matters most:
two hex strings matching only proves arithmetic, whereas a payload that parses
as a UE rep-layout chain and lands on exactly zero bits left is evidence the
whole premise is right.
"""

from __future__ import annotations

import unittest

import pytest

from vrfnet import payload_transform as pt
from vrfnet.bitreader import BitReader

# The reference payload every vector is cut from; each case transforms its
# first `bit_count` bits.  ActorNetGuid is 2, so seed = bit_count ^ 2.
PAYLOAD = bytes.fromhex(
    "BFDF6F9EA1F27BA00000C66EAFAF2E0000339C0DD34B0C45C48063038003562A43C0C949",
)
ACTOR_NET_GUID = 2

VECTORS: tuple[tuple[str, int, str], ...] = (
    # release-12.10
    ("++Ares-Core+release-12.10", 0, ""),
    ("++Ares-Core+release-12.10", 1, "01"),
    ("++Ares-Core+release-12.10", 7, "5F"),
    ("++Ares-Core+release-12.10", 8, "50"),
    ("++Ares-Core+release-12.10", 31, "49629D71"),
    ("++Ares-Core+release-12.10", 32, "A8FC7EF3"),
    ("++Ares-Core+release-12.10", 63, "47D3ED3F73178739"),
    ("++Ares-Core+release-12.10", 64, "10AC2E70AD1212C0"),
    ("++Ares-Core+release-12.10", 65, "7721410F808044D200"),
    (
        "++Ares-Core+release-12.10",
        287,
        "100CA461300F080493400100000040394E5120000000B0792C626000000080FE7F3C2000",
    ),
    (
        "++Ares-Core+release-12.10",
        288,
        "398140967937107E4FA28FEB1FD75CAED71D618B1940D9C6092174B47BA199FD5E2F8393",
    ),
    # release-12.11
    ("++Ares-Core+release-12.11", 0, ""),
    ("++Ares-Core+release-12.11", 1, "01"),
    ("++Ares-Core+release-12.11", 7, "19"),
    ("++Ares-Core+release-12.11", 8, "F4"),
    ("++Ares-Core+release-12.11", 31, "3C77997B"),
    ("++Ares-Core+release-12.11", 32, "18F42FF1"),
    ("++Ares-Core+release-12.11", 63, "8EF2B27ADAE67472"),
    ("++Ares-Core+release-12.11", 64, "D1545FF0BD2FB867"),
    ("++Ares-Core+release-12.11", 65, "E7A9BFB07CFF24CF01"),
    (
        "++Ares-Core+release-12.11",
        287,
        "43FE3C8BA5D21FEFBFA741CE0E0071A3F279A1C6E817075ACF20662447D9E50F75F1481D",
    ),
    (
        "++Ares-Core+release-12.11",
        288,
        "022F9877FE647DE0F27D5FE813C5FC03BA3EA8C3D7C7BB79B8E1C7755F405825611C0C99",
    ),
    # release-13.00
    ("++Ares-Core+release-13.00", 0, ""),
    ("++Ares-Core+release-13.00", 1, "01"),
    ("++Ares-Core+release-13.00", 7, "55"),
    ("++Ares-Core+release-13.00", 8, "88"),
    ("++Ares-Core+release-13.00", 31, "01B0DD66"),
    ("++Ares-Core+release-13.00", 32, "901B662B"),
    ("++Ares-Core+release-13.00", 63, "029693CD8ADFD510"),
    ("++Ares-Core+release-13.00", 64, "224FB261A44ADF65"),
    ("++Ares-Core+release-13.00", 65, "C8336218A9D2979001"),
    (
        "++Ares-Core+release-13.00",
        287,
        "4FE8F025C0F05BA5DBDD798E8A23E32372F1B49C61C270104E7BD61458C2A433218A1A77",
    ),
    (
        "++Ares-Core+release-13.00",
        288,
        "8772F8F262B8A7D2A6703E5E961BA7D703AC43D56EE0CC82F4BE1987FC7847365E6B7C32",
    ),
    # release-13.01
    ("++Ares-Core+release-13.01", 0, ""),
    ("++Ares-Core+release-13.01", 1, "00"),
    ("++Ares-Core+release-13.01", 7, "66"),
    ("++Ares-Core+release-13.01", 8, "33"),
    ("++Ares-Core+release-13.01", 31, "C2B2EA65"),
    ("++Ares-Core+release-13.01", 32, "ABDBCFFA"),
    ("++Ares-Core+release-13.01", 63, "196EDFE8D117154D"),
    ("++Ares-Core+release-13.01", 64, "96407A158400136C"),
    ("++Ares-Core+release-13.01", 65, "9B158480536C754001"),
    (
        "++Ares-Core+release-13.01",
        287,
        "03417AC58400D36B853918CF2FD40E14D17390D76FBE6E2343D7236F626CA9FF9163B932",
    ),
    (
        "++Ares-Core+release-13.01",
        288,
        "7A3611024CB0D5010F95CEE80D1454FC9BFA0206B31864A0621CF3DAE6B7524FDEFA05A3",
    ),
    # release-13.02
    ("++Ares-Core+release-13.02", 0, ""),
    ("++Ares-Core+release-13.02", 1, "00"),
    ("++Ares-Core+release-13.02", 7, "46"),
    ("++Ares-Core+release-13.02", 8, "B3"),
    ("++Ares-Core+release-13.02", 31, "919A9E63"),
    ("++Ares-Core+release-13.02", 32, "9F2ADA1D"),
    ("++Ares-Core+release-13.02", 63, "DA9DA62A9993DA4E"),
    ("++Ares-Core+release-13.02", 64, "5A50DFF6BED22CC7"),
    ("++Ares-Core+release-13.02", 65, "5F6596632DA86F7B01"),
    (
        "++Ares-Core+release-13.02",
        287,
        "B10ED4B77D1031CB749931F80C11719110B1AC15F65AAB929706868895077F43AF407273",
    ),
    (
        "++Ares-Core+release-13.02",
        288,
        "0F926639D681FAB6D03122E222E923CCC987DA22625B2BFC077F432F912DBD96F2368E1E",
    ),
    # release-13.04, and these eleven are a different kind of vector from the
    # fifty-five above.  Upstream has no 13.04, so there is no reference
    # implementation to copy an answer from: these were produced by *our* C#
    # port in the parser clone, which the decoder actually runs.  So they prove
    # the two ports of a derived transform agree byte for byte -- which is the
    # failure this file exists to catch, because a disagreement would scatter
    # coordinates with nothing complaining -- and they prove nothing about
    # whether the transform is right.  What settles that is ground truth:
    # docs/payload-transform-13-04.md carries it.
    ("++Ares-Core+release-13.04", 0, ""),
    ("++Ares-Core+release-13.04", 1, "00"),
    ("++Ares-Core+release-13.04", 7, "62"),
    ("++Ares-Core+release-13.04", 8, "58"),
    ("++Ares-Core+release-13.04", 31, "401FF266"),
    ("++Ares-Core+release-13.04", 32, "FF8A7E7E"),
    ("++Ares-Core+release-13.04", 63, "40B87FB6C26BFE15"),
    ("++Ares-Core+release-13.04", 64, "9810FC015D410C63"),
    ("++Ares-Core+release-13.04", 65, "A610FC0171420C7301"),
    (
        "++Ares-Core+release-13.04",
        287,
        "84E03F1B100292AF828AEACE5D0296906D2C9A6B8E6FB68C5CBBFD3456336D094F1C8E2C",
    ),
    (
        "++Ares-Core+release-13.04",
        288,
        "F40A38092699F880EEF8808AFFFF992BCFD4F45DE7C09B2FD84F63FF135765D4CA9FE1BD",
    ),
)


class TransformVectors(unittest.TestCase):
    def test_known_answers(self):
        # Every vector is checked before reporting: one assert per case would
        # stop at the first failure, and the pattern of which lengths fail is
        # what identifies the broken block.
        wrong = []
        for branch, bits, expected in VECTORS:
            got = pt.decode(PAYLOAD, bits, ACTOR_NET_GUID, branch).hex().upper()
            if got != expected.upper():
                wrong.append((branch, bits, expected.upper(), got))
        assert not wrong, f"{len(wrong)} of {len(VECTORS)} vectors wrong: {wrong[:5]}"

    def test_every_registered_build_is_covered(self):
        # A new transform must arrive with vectors, or it is untested.
        assert {branch for branch, _, _ in VECTORS} == set(pt.SUPPORTED_BRANCHES)


class SubstitutionTables(unittest.TestCase):
    def test_tables_are_permutations(self):
        # A truncated hex literal is still valid hex and still loads, so without
        # this the failure surfaces much later as unexplained decode garbage.
        for table in (
            pt.SUBSTITUTE_TABLE_32,
            pt.SUBSTITUTE_TABLE_64,
            pt.SUBSTITUTE_TABLE_8,
        ):
            assert sorted(table) == list(range(256))


class Registry(unittest.TestCase):
    def test_unknown_build_raises(self):
        # No nearest-version fallback, ever: the mixing differs structurally
        # between builds, so falling back would emit plausible rubbish and make
        # a porting bug look like a version mismatch.  11.11 is the case that
        # actually matters -- the reference library has never covered it.
        with pytest.raises(pt.UnsupportedBuildError, match=r"11.11"):
            pt.transform_for("++Ares-Core+release-11.11")

    def test_seed_is_bit_count_xor_actor(self):
        assert pt.seed_for(287, 2) == 287 ^ 2


class DeobfuscatedPayloadParses(unittest.TestCase):
    def test_handle_chain_terminates_on_zero_bits_left(self):
        bit_count = 287
        clear = pt.decode(
            PAYLOAD,
            bit_count,
            ACTOR_NET_GUID,
            "++Ares-Core+release-12.10",
        )

        reader = BitReader(clear, bit_count)
        reader.read_bit()  # bDoChecksum, one bit, discarded

        chain = []
        while True:
            encoded = reader.read_int_packed()
            if encoded == 0:
                break
            num_bits = reader.read_int_packed()
            chain.append((encoded, num_bits))
            reader.skip_bits(num_bits)

        assert chain == [(4, 3), (13, 3), (15, 8), (19, 192)]
        # Landing exactly on zero is what proves the framing, not the values.
        assert reader.bits_left == 0


class InputHandling(unittest.TestCase):
    def test_zero_bits_is_empty(self):
        assert pt.decode(PAYLOAD, 0, 2, "++Ares-Core+release-12.10") == b""

    def test_short_payload_raises(self):
        with pytest.raises(ValueError, match="need"):
            pt.decode(b"\x01", 64, 2, "++Ares-Core+release-12.10")

    def test_bits_past_the_count_do_not_change_the_result(self):
        # The reference copies into a zeroed buffer, so bits past the count are
        # zero there; letting them through would corrupt the tail XOR.
        noisy = bytearray(PAYLOAD)
        noisy[0] |= 0b1000_0000  # bit 7, past a 7-bit payload
        branch = "++Ares-Core+release-12.10"
        assert pt.decode(bytes(noisy), 7, 2, branch) == pt.decode(PAYLOAD, 7, 2, branch)
