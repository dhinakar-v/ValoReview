"""
Playback packets -> bunches.

Mirrors UNetConnection::ReceivedPacket and FInBunch.  This is where the stream
stops being byte-addressed: a packet is a bag of bits holding one or more
bunches back to back, and a bunch header can start at any bit offset.

Packet termination
------------------
A packet carries no bunch count and no sentinel.  UE terminates it by writing a
single 1 bit after the last bunch and zero-padding to a byte boundary, so the
true bit length is found by scanning the final byte for its highest set bit and
excluding it -- see packet_bit_length().  Getting this wrong makes the bunch
loop try to parse the padding as another bunch, which is exactly the failure
the calibration score is built to detect.

Bunch header
------------
  [bit]   is-ack-dummy                  legacy builds only
  bit     bControl
  bit     bOpen                         only if bControl
  bit     bClose                        only if bControl
  range   CloseReason (max 15)          only if bClose; legacy uses a bDormant bit
  bit     bIsReplicationPaused
  bit     bReliable
  packed  ChIndex                       legacy uses range(10240)
  bits    post-ChIndex flags            bHasPackageMapExports,
                                        bHasMustBeMappedGUIDs, bPartial --
                                        four bits in this build, not three
  bit     bPartialInitial               only if bPartial
  bit     bPartialFinal                 only if bPartial
  FName   ChName                        only if bReliable or bOpen
  range   BunchDataBits (max 16384)
  bits    payload                       exactly BunchDataBits, no terminator
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfnet.bitreader import BitReader, NetError
from vrfnet.versions import (
    CHANNEL_CLOSE_REASON_MAX,
    CHANNEL_TYPE_MAX,
    OLD_MAX_ACTOR_CHANNELS,
    Features,
)

CLOSE_REASON_NAMES = {
    0: "Destroyed",
    1: "Dormancy",
    2: "LevelUnloaded",
    3: "Relevancy",
    4: "TearOff",
}


@dataclass
class Bunch:
    """One FInBunch header plus its payload, still undecoded."""

    ch_index: int
    num_bits: int
    payload_offset: int
    b_open: bool = False
    b_close: bool = False
    b_control: bool = False
    b_reliable: bool = False
    b_partial: bool = False
    b_partial_initial: bool = False
    b_partial_final: bool = False
    b_replication_paused: bool = False
    b_has_package_map_exports: bool = False
    b_has_must_be_mapped_guids: bool = False
    close_reason: int = 0
    ch_name: str = ""
    data: bytes = b""

    @property
    def close_reason_name(self) -> str:
        return CLOSE_REASON_NAMES.get(self.close_reason, f"#{self.close_reason}")

    def reader(self) -> BitReader:
        """A bit cursor over just this bunch's payload."""
        return BitReader(self.data, self.num_bits)


def packet_bit_length(data: bytes) -> int:
    """
    Bit length of a playback packet, excluding UE's terminating 1 bit.

    UE appends a 1 bit after the last bunch then pads the byte with zeros, so
    the last non-zero byte's highest set bit is the terminator.  Returns 0 for
    a packet with no terminator (all-zero), which is malformed.
    """
    end = len(data)
    while end > 0 and data[end - 1] == 0:
        end -= 1
    if end == 0:
        return 0
    last = data[end - 1]
    bit_size = end * 8 - 1
    while not last & 0x80:
        last = (last << 1) & 0xFF
        bit_size -= 1
    return bit_size


def read_bunch_header(reader: BitReader, features: Features) -> Bunch:
    """Read one FInBunch header, leaving the cursor on its payload."""
    if features.legacy_ack_dummy:
        reader.read_bit()

    b_control = reader.read_bool()
    b_open = b_control and reader.read_bool()
    b_close = b_control and reader.read_bool()

    close_reason = 0
    if features.legacy_close_reason:
        if b_close and reader.read_bool():
            close_reason = 1  # Dormancy
    elif b_close:
        close_reason = reader.read_int(CHANNEL_CLOSE_REASON_MAX)

    b_replication_paused = reader.read_bool()
    b_reliable = reader.read_bool()

    if features.legacy_max_channels:
        ch_index = reader.read_int(OLD_MAX_ACTOR_CHANNELS)
    else:
        ch_index = reader.read_int_packed()

    # UE documents three flags here; build release-11.11 carries four.  All
    # four are zero across the whole reference capture -- there are no partial
    # bunches and no inline package-map exports, because the demo ships its
    # exports in the frame prologue instead.  That means the capture does not
    # say which of the four is bPartial, so the assignment below (extras
    # first, bPartial last) is a convention, not a measurement.  It only
    # matters on a replay that actually sets one.
    flags = [reader.read_bool() for _ in range(features.post_chindex_flags)]
    b_has_package_map_exports = flags[0] if flags else False
    b_has_must_be_mapped_guids = flags[1] if len(flags) > 1 else False
    b_partial = flags[-1] if flags else False
    # ChSequence is derived on replay connections, never serialised.
    b_partial_initial = b_partial and reader.read_bool()
    b_partial_final = b_partial and reader.read_bool()

    ch_name = ""
    if features.legacy_channel_names:
        ch_name = f"type#{reader.read_int(CHANNEL_TYPE_MAX)}"
    elif features.chname_always or b_reliable or b_open:
        ch_name = reader.read_fname()

    num_bits = reader.read_int(features.max_packet_bits)

    return Bunch(
        ch_index=ch_index,
        num_bits=num_bits,
        payload_offset=reader.pos,
        b_open=b_open,
        b_close=b_close,
        b_control=b_control,
        b_reliable=b_reliable,
        b_partial=b_partial,
        b_partial_initial=b_partial_initial,
        b_partial_final=b_partial_final,
        b_replication_paused=b_replication_paused,
        b_has_package_map_exports=b_has_package_map_exports,
        b_has_must_be_mapped_guids=b_has_must_be_mapped_guids,
        close_reason=close_reason,
        ch_name=ch_name,
    )


def read_packet_bunches(
    data: bytes,
    features: Features,
    *,
    keep_payload: bool = True,
) -> list[Bunch]:
    """
    Split one playback packet into bunches.

    Raises NetError on any desync; callers that are scoring rather than
    decoding should catch it and count the packet as failed.
    """
    num_bits = packet_bit_length(data)
    if num_bits == 0:
        return []
    reader = BitReader(data, num_bits)
    bunches: list[Bunch] = []
    while not reader.at_end():
        bunch = read_bunch_header(reader, features)
        if bunch.num_bits > reader.bits_left:
            msg = (
                f"bunch wants {bunch.num_bits} bits, packet has {reader.bits_left} left"
            )
            raise NetError(msg)
        if keep_payload:
            bunch.data = reader.read_bits_bytes(bunch.num_bits)
        else:
            reader.skip_bits(bunch.num_bits)
        bunches.append(bunch)
    return bunches


@dataclass
class PacketScore:
    """How cleanly a Features candidate parses a body of packets."""

    features: Features
    total: int = 0
    clean: int = 0
    bunches: int = 0
    failures: dict[str, int] = field(default_factory=dict)

    @property
    def rate(self) -> float:
        return self.clean / self.total if self.total else 0.0

    def note_failure(self, exc: Exception) -> None:
        key = type(exc).__name__
        self.failures[key] = self.failures.get(key, 0) + 1


def score_features(
    packets,
    features: Features,
    limit: int | None = None,
) -> PacketScore:
    """
    Fraction of packets whose bunch loop lands exactly on at_end().

    This is the calibration metric and, later, the health metric for the whole
    decoder: bit-level desync is not subtle, it collapses this number.
    """
    score = PacketScore(features=features)
    for i, packet in enumerate(packets):
        if limit is not None and i >= limit:
            break
        score.total += 1
        try:
            bunches = read_packet_bunches(packet.data, features, keep_payload=False)
        except NetError as exc:
            score.note_failure(exc)
            continue
        score.clean += 1
        score.bunches += len(bunches)
    return score
