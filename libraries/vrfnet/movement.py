"""
Player movement: the one place this pipeline learns where anybody is.

Positions do not arrive as a replicated property.  They ride an RPC --
`ReplaysClientReceiveRemoteCharacterUpdatesSingleArrayNoAutonomous`, 17,164
invocations carrying 60.6 million bits on the reference 12.10 capture -- whose
payload nests three levels deep:

    RPC payload         one checksum bit, then (handle, bits) pairs;
                        handle 1 is the update array
      update array      a packed count, then (index, bits) per update
        update          (handle, bits) pairs; handle 2 is the character's net
                        GUID, handle 3 is the movement bitstream below

The movement bitstream is its own format and not UE's: a magic byte, then moves
delimited by a 3-bit marker that cycles 1..7 and never returns to 0 except to
end the run.  That marker sequence is the only integrity check available here,
so a mismatch aborts the record rather than resyncing -- a desynced move would
still produce plausible coordinates, which is worse than none.

Each move carries a position quantised at 1/100 of an Unreal unit and a packed
yaw/pitch dword.  Velocity only appears on move type 1.  A move ends with an
error sentinel bit that the game itself sets when it knows the record is bad;
when it is set the move is discarded.

Ported from ValorantReplayParser (MIT, Copyright (c) 2026 Michel Giehl):
  src/Replay.Valorant/Movement/RemoteCharacterUpdatesRpcDecoder.cs
  src/Replay.Valorant/Movement/ComponentDataStream.cs
See THIRD_PARTY.md.  Two upstream quirks are deliberately not reproduced: it
passes `movementState` for both its mode and state fields, and its
`Vector100` decoder is actually scale 10.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfnet.bitreader import BitReader, NetError

# The one RPC that carries player positions.  Named here so the session can
# recognise it without importing the schema layer.
MOVEMENT_RPC = "ReplaysClientReceiveRemoteCharacterUpdatesSingleArrayNoAutonomous"

MOVEMENT_MAGIC = 0x52
FIXED_VECTOR_SCALE = 1.0 / 65536.0
ANGLE_SCALE = 360.0 / 65536.0
POSITION_SCALE = 100
VELOCITY_SCALE = 10

# Once fewer than this many bits remain, what is left is padding, not a move.
MAX_MOVEMENT_PADDING_BITS = 31
MAX_REMOTE_CHARACTER_UPDATES = 256

# Handles inside the RPC payload, after the 1-based wire handle is decremented.
UPDATES_HANDLE = 1
SHOOTER_GUID_HANDLE = 2
COMPONENT_DATA_HANDLE = 3

MOVE_HEADER_BITS = 25
ANGLE_FIELD_BITS = 33
FIXED_VECTOR_BITS = 48
QUANTIZED_PREFIX_BITS = 7
MAX_COMPONENT_BITS = 62

# A VLQ that has shifted this far cannot fit the uint32 it decodes into.
VLQ_MAX_SHIFT = 32
# Marker 0 ends a run, so the cycle skips it and restarts at 1.
FIRST_MARKER = 1
# One spare byte after the update list is padding the writer emitted.
PAD_BYTE_BITS = 8


@dataclass(frozen=True)
class Vector:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class Move:
    """One movement record: where a character was, and which way it faced."""

    marker: int
    timestamp: int
    position: Vector
    yaw: float
    pitch: float
    move_type: int
    movement_state: int
    velocity: Vector | None = None

    @property
    def described(self) -> str:
        return (
            f"t={self.timestamp} "
            f"({self.position.x:9.1f}, {self.position.y:9.1f}, {self.position.z:7.1f}) "
            f"yaw={self.yaw:6.1f}"
        )


@dataclass
class ComponentData:
    """The movement bitstream for one character in one update."""

    moves: list[Move] = field(default_factory=list)
    magic_ok: bool = False
    error: str = ""

    @property
    def latest(self) -> Move | None:
        return self.moves[-1] if self.moves else None


@dataclass(frozen=True)
class CharacterUpdate:
    """One character's slice of a movement batch."""

    index: int
    shooter_guid: int = 0
    data: ComponentData | None = None


@dataclass
class MovementBatch:
    """Every character updated by one RPC invocation."""

    updates: list[CharacterUpdate] = field(default_factory=list)
    error: str = ""

    @property
    def moves(self) -> int:
        return sum(len(u.data.moves) for u in self.updates if u.data is not None)


def _sub(reader: BitReader, num_bits: int) -> BitReader:
    """A reader over the next `num_bits`, so a nested field cannot overrun."""
    return BitReader(reader.read_bits_bytes(num_bits), num_bits)


def _sign_extend(raw: int, bit_count: int) -> int:
    sign_bit = 1 << (bit_count - 1)
    return (raw ^ sign_bit) - sign_bit


def _read_vlq(reader: BitReader) -> int:
    """Byte-oriented VLQ whose continuation flag is the low bit, not the high."""
    value = 0
    shift = 0
    while True:
        byte = reader.read_u8()
        value |= ((byte >> 1) & 0x7F) << shift
        if not byte & 1:
            return value
        shift += 7
        if shift >= VLQ_MAX_SHIFT:
            msg = "movement timestamp VLQ too long"
            raise NetError(msg)


def _read_fixed_vector(reader: BitReader) -> Vector:
    bits = reader.read_bits(FIXED_VECTOR_BITS)
    parts = [(bits >> (16 * i)) & 0xFFFF for i in range(3)]
    return Vector(*[(p - 0x8000) * FIXED_VECTOR_SCALE for p in parts])


def _read_quantized_vector(reader: BitReader, scale: int) -> Vector:
    """
    UE's `FVector_NetQuantize` shape: a width prefix, then three signed ints.

    A zero width is the escape hatch to raw floats, which is why a position can
    still be exact when the quantiser cannot represent it.
    """
    prefix = reader.read_bits(QUANTIZED_PREFIX_BITS)
    component_bits = prefix & 63
    scaled = prefix >> 6

    if component_bits > 0:
        if component_bits > MAX_COMPONENT_BITS:
            msg = f"quantised vector claims {component_bits} bits per component"
            raise NetError(msg)
        raw = reader.read_bits(component_bits * 3)
        mask = (1 << component_bits) - 1
        parts = [
            _sign_extend((raw >> (component_bits * i)) & mask, component_bits)
            for i in range(3)
        ]
        if scaled:
            return Vector(*[p / scale for p in parts])
        return Vector(*[float(p) for p in parts])

    if scaled:
        msg = "double-precision movement vector is not decoded"
        raise NetError(msg)
    return Vector(*[reader.read_f32() for _ in range(3)])


def _read_move(reader: BitReader, marker: int) -> Move:
    header = reader.read_bits(MOVE_HEADER_BITS)
    move_type = header & 1
    movement_state = (header >> 9) & 0xFF

    _read_fixed_vector(reader)  # rotation input; superseded by the packed angles
    timestamp = _read_vlq(reader)
    position = _read_quantized_vector(reader, POSITION_SCALE)

    if reader.read_bit():
        reader.read_u8()  # optional byte, meaning unknown

    packed = reader.read_bits(ANGLE_FIELD_BITS) >> 1
    pitch = packed & 0xFFFF
    yaw = packed >> 16

    velocity = None
    if move_type:
        reader.read_bit()
        velocity = _read_quantized_vector(reader, VELOCITY_SCALE)
    else:
        extra = reader.read_bits(ANGLE_FIELD_BITS)
        if extra & 1:
            msg = "variant-0 external character reference is not decoded"
            raise NetError(msg)

    if reader.read_bit():
        # The game marks its own record bad; trust it and drop the move.
        msg = "movement error sentinel was set"
        raise NetError(msg)

    return Move(
        marker=marker,
        timestamp=timestamp,
        position=position,
        yaw=yaw * ANGLE_SCALE,
        pitch=pitch * ANGLE_SCALE,
        move_type=move_type,
        movement_state=movement_state,
        velocity=velocity,
    )


def _next_marker(marker: int) -> int:
    nxt = (marker + 1) & 7
    return max(FIRST_MARKER, nxt)


def _read_movement_section(reader: BitReader) -> ComponentData:
    out = ComponentData()
    try:
        magic = reader.read_u8()
    except NetError:
        out.error = "missing movement magic"
        return out
    out.magic_ok = magic == MOVEMENT_MAGIC
    if not out.magic_ok:
        out.error = f"invalid movement magic 0x{magic:02X}"
        return out

    expected = 1
    try:
        marker = reader.read_bits(3)
        while marker != 0:
            if marker != expected:
                out.error = f"marker mismatch: expected {expected}, got {marker}"
                return out
            out.moves.append(_read_move(reader, marker))
            if reader.bits_left <= MAX_MOVEMENT_PADDING_BITS:
                return out
            expected = _next_marker(expected)
            marker = reader.read_bits(3)
    except (NetError, ValueError) as exc:
        out.error = str(exc)
    return out


def _read_component_payload(reader: BitReader) -> ComponentData:
    try:
        movement_bits = reader.read_u16()
    except NetError:
        return ComponentData(error="missing movement bit count")
    if movement_bits == 0 or movement_bits > reader.bits_left:
        return _read_movement_section(reader)
    return _read_movement_section(_sub(reader, movement_bits))


def read_component_data(payload: bytes, num_bits: int) -> ComponentData:
    """
    Decode one `ComponentDataStream`.

    The payload is sometimes wrapped in a byte count and sometimes not, and
    nothing distinguishes the two but plausibility, so the wrapped reading is
    attempted first and abandoned if the count does not fit.
    """
    reader = BitReader(payload, num_bits)
    try:
        byte_count = reader.read_u16()
    except NetError:
        byte_count = 0
    if byte_count and reader.bits_left >= byte_count * 8:
        return _read_component_payload(_sub(reader, byte_count * 8))
    return _read_component_payload(BitReader(payload, num_bits))


def _read_update(reader: BitReader, index: int) -> CharacterUpdate:
    guid = 0
    data: ComponentData | None = None
    while reader.bits_left > 0:
        encoded = reader.read_int_packed()
        if encoded == 0:
            break
        handle = encoded - 1
        num_bits = reader.read_int_packed()
        if num_bits > reader.bits_left:
            break
        payload = reader.read_bits_bytes(num_bits)
        if handle == SHOOTER_GUID_HANDLE:
            guid = BitReader(payload, num_bits).read_u32()
        elif handle == COMPONENT_DATA_HANDLE:
            data = read_component_data(payload, num_bits)
    return CharacterUpdate(index=index, shooter_guid=guid, data=data)


def _read_updates(reader: BitReader) -> list[CharacterUpdate]:
    count = reader.read_int_packed()
    if count > MAX_REMOTE_CHARACTER_UPDATES:
        msg = f"movement batch claims {count} updates"
        raise NetError(msg)
    updates: list[CharacterUpdate] = []
    while reader.bits_left > 0:
        encoded = reader.read_int_packed()
        if encoded == 0:
            # A lone trailing byte here is padding the writer emitted.
            if reader.bits_left == PAD_BYTE_BITS:
                reader.read_int_packed()
            break
        index = encoded - 1
        if index >= count:
            break
        updates.append(_read_update(reader, index))
    return updates


def read_movement_rpc(payload: bytes, num_bits: int) -> MovementBatch:
    """
    Decode one `...ReceiveRemoteCharacterUpdates...` invocation.

    Returns an empty batch rather than raising when the payload is not what it
    claims: movement is one signal among many, and losing an RPC should cost a
    frame of positions, not the replay.
    """
    batch = MovementBatch()
    reader = BitReader(payload, num_bits)
    try:
        reader.read_bit()  # checksum bit, as on every property payload
        while reader.bits_left > 0:
            encoded = reader.read_int_packed()
            if encoded == 0:
                break
            handle = encoded - 1
            field_bits = reader.read_int_packed()
            if field_bits > reader.bits_left:
                batch.error = f"rpc field wants {field_bits} bits"
                return batch
            inner = _sub(reader, field_bits)
            if handle == UPDATES_HANDLE:
                batch.updates.extend(_read_updates(inner))
    except (NetError, ValueError) as exc:
        batch.error = str(exc)
    return batch


@dataclass
class MovementLog:
    """
    Every decoded move, grouped by the character it belongs to.

    Keyed by the character's net GUID rather than by channel, because that is
    the identity the rest of the pipeline already joins on: it is the same
    number `characterDeath` events carry.
    """

    samples: dict[int, list[tuple[float, Move]]] = field(default_factory=dict)
    batches: int = 0
    batches_failed: int = 0
    updates: int = 0
    streams_failed: int = 0

    @property
    def moves(self) -> int:
        return sum(len(v) for v in self.samples.values())

    @property
    def characters(self) -> int:
        return len(self.samples)

    def add(self, time_seconds: float, batch: MovementBatch) -> None:
        self.batches += 1
        if batch.error:
            self.batches_failed += 1
        for update in batch.updates:
            self.updates += 1
            if update.data is None:
                continue
            if update.data.error:
                self.streams_failed += 1
            if not update.data.moves:
                continue
            bucket = self.samples.setdefault(update.shooter_guid, [])
            bucket.extend((time_seconds, move) for move in update.data.moves)

    def bounds(self, guid: int) -> tuple[float, float, float, float]:
        """(min x, max x, min y, max y) for one character, for sanity checks."""
        moves = [m for _t, m in self.samples.get(guid, ())]
        if not moves:
            return (0.0, 0.0, 0.0, 0.0)
        xs = [m.position.x for m in moves]
        ys = [m.position.y for m in moves]
        return (min(xs), max(xs), min(ys), max(ys))

    def report(self) -> str:
        lines = [
            f"movement rpcs     {self.batches:,} ({self.batches_failed:,} failed)",
            f"character updates {self.updates:,} ({self.streams_failed:,} failed)",
            f"moves             {self.moves:,} over {self.characters} characters",
        ]
        return "\n".join(lines)
