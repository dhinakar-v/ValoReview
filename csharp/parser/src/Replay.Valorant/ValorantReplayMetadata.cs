using Replay.Models.Replay;

namespace Replay.Valorant;

public enum ValorantReplaySupportStatus
{
    Supported,
    UnsupportedVersion,
}

public sealed record ValorantReplayMetadata(
    ReplayInfo ReplayInfo,
    ReplayInfoSerializationMetadata ReplayInfoSerializationMetadata,
    ReplayHeader ReplayHeader,
    ReplayVersion ReplayVersion,
    UEVersion UEVersion,
    ValorantReplaySupportStatus FullParseSupportStatus,
    string? FullParseUnsupportedReason);
