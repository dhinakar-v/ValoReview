"""
Engine network-version gating.

The capture reports network version 480767974 for build ++Ares-Core+release-11.11,
but the EEngineNetworkVersionHistory integer thresholds for that build are not
public (docs/vrf-decoding-research.md, Open Questions).  Guessing them would
put an unverified constant underneath the entire decoder.

So the gates are not guessed.  Features is a plain policy object, and
vrfnet.calibrate resolves it empirically: it sweeps every combination against
real packets and scores each by how many bunch loops consume to exactly zero
leftover bits.  A wrong bit layout desyncs within a bunch or two and scores
near zero, so the correct combination separates by a wide margin.

Each flag names the UE history gate it stands for, so if Riot bumps the engine
the failing branch is obvious.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# UE's own bounds, used by the range-coded integers in a bunch header.
OLD_MAX_ACTOR_CHANNELS = 10240
CHANNEL_CLOSE_REASON_MAX = 15  # EChannelCloseReason::MAX
CHANNEL_TYPE_MAX = 8  # EChannelType::CHTYPE_MAX


@dataclass(frozen=True)
class Features:
    """Which side of each version gate this capture sits on.

    Defaults are the modern branch, which release-11.11 is expected to take;
    calibration confirms or overrides them.
    """

    # < HISTORY_ACKS_INCLUDED_IN_HEADER: a leading "is ack dummy" bit.
    legacy_ack_dummy: bool = False
    # < HISTORY_CHANNEL_CLOSE_REASON: a bDormant bit instead of a close reason.
    legacy_close_reason: bool = False
    # < HISTORY_MAX_ACTOR_CHANNELS_CUSTOMIZATION: fixed-width ChIndex.
    legacy_max_channels: bool = False
    # < HISTORY_CHANNEL_NAMES: an integer ChType instead of an FName ChName.
    legacy_channel_names: bool = False
    # Flag bits between ChIndex and the partial flags.  UE documents three
    # (bHasPackageMapExports, bHasMustBeMappedGUIDs, bPartial); this build
    # carries four.  All four are zero throughout the reference capture, so
    # which of them is bPartial is not determined by it -- see datachannel.
    post_chindex_flags: int = 4
    # Read ChName unconditionally rather than only for reliable/opening bunches.
    chname_always: bool = False
    # UNetConnection::MaxPacketSizeInBits, the bound on the bunch length field.
    max_packet_bits: int = 16384

    def as_dict(self) -> dict:
        return asdict(self)

    def describe(self) -> str:
        parts = [
            f"ack_dummy={'legacy' if self.legacy_ack_dummy else 'modern'}",
            f"close_reason={'legacy' if self.legacy_close_reason else 'modern'}",
            f"ch_index={'fixed' if self.legacy_max_channels else 'packed'}",
            f"ch_name={'ChType' if self.legacy_channel_names else 'FName'}",
            f"post_flags={self.post_chindex_flags}",
            f"chname={'always' if self.chname_always else 'if-reliable-or-open'}",
            f"max_packet_bits={self.max_packet_bits}",
        ]
        return " ".join(parts)


def candidate_features() -> list[Features]:
    """Every combination the calibration sweep considers."""
    out = []
    for ack in (False, True):
        for close in (False, True):
            for chidx in (False, True):
                for chname in (False, True):
                    for post in (3, 4, 5):
                        for always in (False, True):
                            for bits in (16384, 8192):
                                out.append(
                                    Features(
                                        legacy_ack_dummy=ack,
                                        legacy_close_reason=close,
                                        legacy_max_channels=chidx,
                                        legacy_channel_names=chname,
                                        post_chindex_flags=post,
                                        chname_always=always,
                                        max_packet_bits=bits,
                                    )
                                )
    return out
