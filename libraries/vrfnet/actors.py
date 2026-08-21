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

What this module does not decode
--------------------------------
The interior of a content-block payload -- but only because that belongs to
vrfnet.properties now, not because it is out of reach.  This module reports a
ContentBlock and stops.

That is a change of position.  This docstring used to record that the payload
did not parse at all: that the documented [packed handle][packed NumBits]
[payload] loop yielded implausible values, billions rather than small handles.
The reading was right and the conclusion was wrong -- the bytes were
obfuscated, and billions is exactly what a correct packed-int reader returns on
a keystream.  vrfnet.payload_transform undoes it; the loop underneath is the
documented one after all.

The spawn transform on an opening bunch is still not decoded, and that one is a
genuine gap: it was searched for exhaustively across 2,700 offset and scale
combinations against known coordinates and is not present at any fixed offset
in the form UE documents.  read_new_actor therefore stops after the archetype.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from vrfnet.bitreader import BitReader, NetError

if TYPE_CHECKING:
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
    """
    UPackageMapClient::SerializeNewActor, as far as identity goes.

    Reads the actor and archetype GUIDs.  Whatever follows them is not
    decoded: UE would put a spawn transform there, but a sweep of 2,700
    offset and scale combinations against known coordinates found no location
    at any fixed offset, so the cursor is left immediately after the archetype
    -- enough for identity, not enough to reach the content blocks of an
    opening bunch.  Positions come from the movement RPC instead; see
    vrfnet.movement.
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
        msg = f"content block wants {num_bits} bits, {reader.bits_left} left"
        raise NetError(msg)
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
    # Actor net GUID -> archetype path, for every actor ever opened.  Kept
    # apart from `channels` because that table is not a history: a channel is
    # dropped when the actor disconnects and the whole table is cleared at a
    # checkpoint, but who an actor was does not stop being true, and a
    # consumer reading identities at the end of a run needs all of them.
    archetypes: dict[int, str] = field(default_factory=dict)

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
        if actor.archetype_path:
            self.archetypes[actor.actor_guid] = actor.archetype_path
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
        """
        A checkpoint drops every channel-to-actor association.

        `archetypes` deliberately survives: the channel indices are what a
        checkpoint invalidates, not the identity of the actors they carried.
        """
        self.channels.clear()

    def by_archetype(self) -> dict[str, list[Channel]]:
        out: dict[str, list[Channel]] = {}
        for channel in self.channels.values():
            out.setdefault(channel.archetype_path or "<unresolved>", []).append(channel)
        return out
