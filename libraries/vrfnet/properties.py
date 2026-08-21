"""
The property loop inside a content block, once the payload is de-obfuscated.

`payload_transform` is what makes this module possible: the bits arriving from
`actors.read_content_block` are whitened, and every handle read out of them is
noise until the transform is undone.  Measured on a real 12.10 capture, the raw
bits yield 0 clean parses in 33,655 content blocks and the de-obfuscated bits
yield 99.75% across the rep-layout ones.

There are two encodings here, not one, and the content block header says which:

  rep-layout        one bDoChecksum bit, then repeating
                    (packed handle, packed NumBits, NumBits of value),
                    terminated by handle 0.  Handles are 1-based on the wire.

  class net cache   a range-coded handle over the group's export count, then
                    packed NumBits.  This is the RPC path, and it is the one
                    player movement arrives on, so it is not optional.

Nothing here interprets a value.  A field is (handle, bits) and the bits stay
opaque, exactly as `actors.py` leaves the payload -- naming a handle needs the
export table, and decoding its bits needs a schema.  Keeping the split means a
wrong schema can never corrupt the framing, only the reading of it.

The `exact` flag is the health metric for this layer, and it is a genuinely
different one from `clean_packet_rate`: that is computed from bunch *headers*
and never enters a payload, so it cannot see a property-layout error at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vrfnet import payload_transform
from vrfnet.bitreader import BitReader, NetError

REP_LAYOUT = "rep-layout"
CLASS_NET_CACHE = "class-net-cache"

# A rep-layout chain ends on handle 0.  Nothing else terminates it.
TERMINATOR = 0

# The RPC chain has no terminator: it ends when too few bits remain for a
# NumBits field, so anything shorter than this is the block's padding.
MIN_RPC_TAIL_BITS = 8

# Failure kinds worth listing; the rest are summarised.
TOP_FAILURES = 6


@dataclass(frozen=True)
class PropertyField:
    """One replicated property: which one, and its still-opaque bits."""

    handle: int
    num_bits: int
    payload: bytes
    name: str = ""

    @property
    def described(self) -> str:
        return f"{self.handle}:{self.name}" if self.name else str(self.handle)


@dataclass(frozen=True)
class PropertyBlock:
    """The outcome of reading one content block payload."""

    kind: str
    fields: tuple[PropertyField, ...] = ()
    exact: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        """A block is only trusted when it consumed its payload exactly."""
        return self.exact and not self.error


@dataclass
class PropertyStats:
    """Counters for the property layer, kept apart from the bunch-level ones."""

    blocks: int = 0
    blocks_ok: int = 0
    rep_layout: int = 0
    rep_layout_ok: int = 0
    class_net_cache: int = 0
    class_net_cache_ok: int = 0
    fields: int = 0
    fields_named: int = 0
    failures: dict[str, int] = field(default_factory=dict)

    def fail(self, reason: str) -> None:
        self.failures[reason] = self.failures.get(reason, 0) + 1

    @property
    def ok_rate(self) -> float:
        return self.blocks_ok / self.blocks if self.blocks else 0.0

    @property
    def rep_layout_rate(self) -> float:
        return self.rep_layout_ok / self.rep_layout if self.rep_layout else 0.0

    @property
    def class_net_cache_rate(self) -> float:
        return (
            self.class_net_cache_ok / self.class_net_cache
            if self.class_net_cache
            else 0.0
        )

    def record(self, block: PropertyBlock) -> None:
        self.blocks += 1
        if block.kind == REP_LAYOUT:
            self.rep_layout += 1
            self.rep_layout_ok += block.ok
        else:
            self.class_net_cache += 1
            self.class_net_cache_ok += block.ok
        self.blocks_ok += block.ok
        self.fields += len(block.fields)
        self.fields_named += sum(1 for f in block.fields if f.name)
        if block.error:
            self.fail(block.error)

    def report(self) -> str:
        lines = [
            f"property blocks   {self.blocks:,} ({self.ok_rate:.2%} exact)",
            (
                f"  rep layout      {self.rep_layout:,} "
                f"({self.rep_layout_rate:.2%} exact)"
            ),
            (
                f"  class net cache {self.class_net_cache:,} "
                f"({self.class_net_cache_rate:.2%} exact)"
            ),
            f"fields            {self.fields:,} ({self.fields_named:,} named)",
        ]
        if self.failures:
            # Bit counts read out of a mis-framed block are effectively
            # unique, so the long tail is one line per block and says
            # nothing that the total does not.
            ranked = sorted(self.failures.items(), key=lambda kv: -kv[1])
            total = sum(self.failures.values())
            lines.append(f"property failures ({total:,}):")
            lines += [f"  {count:>7,}  {key}" for key, count in ranked[:TOP_FAILURES]]
            if len(ranked) > TOP_FAILURES:
                rest = sum(c for _k, c in ranked[TOP_FAILURES:])
                kinds = len(ranked) - TOP_FAILURES
                lines.append(f"  {rest:>7,}  ... and {kinds} rarer kinds")
        return "\n".join(lines)


def _name_for(group, handle: int) -> str:
    if group is None:
        return ""
    export = group.lookup(handle)
    return export.name if export is not None else ""


def read_rep_layout(reader: BitReader, group=None) -> PropertyBlock:
    """
    The state path: checksum bit, then handle/NumBits pairs until handle 0.

    A truncated or mis-framed chain is reported rather than raised: one bad
    block should cost that block, not the replay, exactly as the bunch layer
    treats a bad packet.
    """
    fields: list[PropertyField] = []
    try:
        reader.read_bit()  # bDoChecksum; the checksum itself is not written
        while True:
            handle = reader.read_int_packed()
            if handle == TERMINATOR:
                break
            num_bits = reader.read_int_packed()
            if num_bits > reader.bits_left:
                return PropertyBlock(
                    kind=REP_LAYOUT,
                    fields=tuple(fields),
                    error=f"field wants {num_bits} bits, {reader.bits_left} left",
                )
            fields.append(
                PropertyField(
                    handle=handle,
                    num_bits=num_bits,
                    payload=reader.read_bits_bytes(num_bits),
                    name=_name_for(group, handle),
                ),
            )
    except (NetError, ValueError) as exc:
        return PropertyBlock(kind=REP_LAYOUT, fields=tuple(fields), error=str(exc))
    return PropertyBlock(
        kind=REP_LAYOUT,
        fields=tuple(fields),
        exact=reader.bits_left == 0,
    )


def read_class_net_cache(reader: BitReader, group=None) -> PropertyBlock:
    """
    The RPC path: a range-coded handle, then packed NumBits, repeating.

    Unlike the rep-layout chain there is no terminator -- the block ends when
    the bits do -- and the handle's width depends on the group's export count,
    so without a group this cannot be read at all.
    """
    num_functions = getattr(group, "num_exports", 0) if group is not None else 0
    if num_functions <= 0:
        return PropertyBlock(kind=CLASS_NET_CACHE, error="no export group")

    fields: list[PropertyField] = []
    try:
        while reader.bits_left > 0:
            try:
                handle = reader.read_int(num_functions)
            except NetError:
                # UE reads a ranged int bit by bit, so a handle can run off the
                # end of the block.  That is the padding, not a truncated call.
                break
            # Likewise, fewer than 8 bits after a handle cannot hold a NumBits.
            # This is the normal way the chain ends: there is no terminator
            # handle on this path, unlike rep layout.
            if reader.bits_left < MIN_RPC_TAIL_BITS:
                break
            num_bits = reader.read_int_packed()
            if num_bits > reader.bits_left:
                return PropertyBlock(
                    kind=CLASS_NET_CACHE,
                    fields=tuple(fields),
                    error=f"rpc wants {num_bits} bits, {reader.bits_left} left",
                )
            fields.append(
                PropertyField(
                    handle=handle,
                    num_bits=num_bits,
                    payload=reader.read_bits_bytes(num_bits),
                    name=_name_for(group, handle),
                ),
            )
    except (NetError, ValueError) as exc:
        return PropertyBlock(kind=CLASS_NET_CACHE, fields=tuple(fields), error=str(exc))
    # Reaching here means the chain ended the only way it can: it ran out of
    # room for another call.  Unlike rep layout there is no terminator, so
    # leftover padding bits are correct rather than a shortfall.
    return PropertyBlock(kind=CLASS_NET_CACHE, fields=tuple(fields), exact=True)


def decode_content_block(
    block,
    actor_guid: int,
    branch: str,
    group=None,
) -> PropertyBlock:
    """
    De-obfuscate one content block and read its properties.

    `block.flag_a` is bHasRepLayout.  That identification is measured, not
    assumed: on a 12.10 capture the flag_a=True blocks parse as rep-layout
    chains 99.75% of the time and the flag_a=False ones 40%, which is what a
    different encoding sharing a terminator-free tail looks like.
    """
    if block.num_bits <= 0:
        return PropertyBlock(kind=REP_LAYOUT, exact=True)
    try:
        clear = payload_transform.decode(
            block.payload,
            block.num_bits,
            actor_guid,
            branch,
        )
    except payload_transform.UnsupportedBuildError:
        raise
    except ValueError as exc:
        return PropertyBlock(kind=REP_LAYOUT, error=f"transform: {exc}")

    reader = BitReader(clear, block.num_bits)
    if block.flag_a:
        return read_rep_layout(reader, group)
    return read_class_net_cache(reader, group)
