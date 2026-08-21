"""
Actor channels: spawn identity and content-block framing.

Mirrors UActorChannel.  A bunch's payload is one or more content blocks; an
opening bunch prefixes them with the actor's spawn record.

What is verified against the reference capture
----------------------------------------------
SerializeNewActor -- an opening bunch's payload begins with exactly two packed
NetGUIDs, the actor and its archetype.  Validated by resolution rather than by
bit accounting: 261 of 286 opening bunches yield an archetype GUID that is
already in the GUID cache with a real /Game or /Script path, and the paths are
UE class default objects (Default__Foo_C), which is what an archetype is.  The
25 that do not resolve are actors whose archetype was exported in a block not
yet read.  Actor GUIDs are dynamic (even, runtime-assigned) and correctly have
no exported path.

Content block framing -- a non-opening bunch's payload is two flag bits then a
packed NumPayloadBits that covers the remainder of the bunch exactly.  Verified
on 6,517 of 8,000 sampled bunches (81.4%); a length field that lands exactly on
the bunch boundary that often is not a coincidence.

What is NOT decoded
-------------------
The interior of a content-block payload.  docs/vrf-decoding-research.md Part 1
predicts a flat [packed handle][packed NumBits][payload] loop terminated by
handle 0, which would make every property skippable without a schema.  That
loop does not parse here: across both flag groups, zero payloads consume
cleanly, and the leading packed integers decode to implausible values (billions)
rather than small handles.  So for this title the property payload is not
self-delimiting in the documented way, and read_properties below deliberately
does not pretend otherwise -- it reports the payload rather than guessing at it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfnet.bitreader import BitReader, NetError
from vrfnet.datachannel import Bunch
from vrfnet.packagemap import GuidCache


@dataclass
class NewActor:
    """The spawn record at the head of an opening bunch."""

    actor_guid: int
    archetype_guid: int
    archetype_path: str = ""

    @property
    def resolved(self) -> bool:
        return bool(self.archetype_path)


@dataclass
class ContentBlock:
    """One content block: two header flags and its still-opaque payload."""

    flag_a: bool
    flag_b: bool
    num_bits: int
    payload: bytes
    exact: bool = False

    def reader(self) -> BitReader:
        return BitReader(self.payload, self.num_bits)


@dataclass
class Channel:
    """A live actor channel, from its opening bunch to its close."""

    ch_index: int
    actor_guid: int = 0
    archetype_guid: int = 0
    archetype_path: str = ""
    opened_at: float = 0.0
    bunches: int = 0
    content_blocks: int = 0
    payload_bits: int = 0


def read_new_actor(reader: BitReader, cache: GuidCache) -> NewActor:
    """UPackageMapClient::SerializeNewActor, as far as identity goes.

    Reads the actor and archetype GUIDs.  The spawn transform that follows
    (location/rotation/scale/velocity, each behind a presence bit and encoded
    as a quantised vector) is not decoded, so the cursor is left immediately
    after the archetype -- enough for identity, not enough to reach the
    content blocks of an opening bunch.
    """
    actor_guid = reader.read_int_packed()
    archetype_guid = reader.read_int_packed()
    return NewActor(
        actor_guid=actor_guid,
        archetype_guid=archetype_guid,
        archetype_path=cache.full_path(archetype_guid),
    )


def read_content_block(reader: BitReader) -> ContentBlock:
    """Two header flags, then a packed length covering the payload."""
    flag_a = reader.read_bool()
    flag_b = reader.read_bool()
    num_bits = reader.read_int_packed()
    if num_bits > reader.bits_left:
        raise NetError(
            f"content block wants {num_bits} bits, {reader.bits_left} left"
        )
    exact = num_bits == reader.bits_left
    return ContentBlock(
        flag_a=flag_a,
        flag_b=flag_b,
        num_bits=num_bits,
        payload=reader.read_bits_bytes(num_bits),
        exact=exact,
    )


@dataclass
class ChannelTable:
    """ChIndex -> Channel, reset whenever a checkpoint reseeds the world."""

    channels: dict[int, Channel] = field(default_factory=dict)
    opened: int = 0
    closed: int = 0
    resolved: int = 0
    unresolved: int = 0

    def __len__(self) -> int:
        return len(self.channels)

    def open(self, bunch: Bunch, actor: NewActor, time_seconds: float) -> Channel:
        channel = Channel(
            ch_index=bunch.ch_index,
            actor_guid=actor.actor_guid,
            archetype_guid=actor.archetype_guid,
            archetype_path=actor.archetype_path,
            opened_at=time_seconds,
        )
        self.channels[bunch.ch_index] = channel
        self.opened += 1
        if actor.resolved:
            self.resolved += 1
        else:
            self.unresolved += 1
        return channel

    def close(self, ch_index: int) -> None:
        if self.channels.pop(ch_index, None) is not None:
            self.closed += 1

    def get(self, ch_index: int) -> Channel | None:
        return self.channels.get(ch_index)

    def reset(self) -> None:
        """A checkpoint drops every channel-to-actor association."""
        self.channels.clear()

    def by_archetype(self) -> dict[str, list[Channel]]:
        out: dict[str, list[Channel]] = {}
        for channel in self.channels.values():
            out.setdefault(channel.archetype_path or "<unresolved>", []).append(
                channel
            )
        return out
