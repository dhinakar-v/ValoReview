using Replay.Models.Replay;

namespace Replay.Unreal.Chunks;

public sealed record ReplayPreambleReadResult(
    ReplayInfo ReplayInfo,
    ReplayInfoSerializationMetadata ReplayInfoSerializationMetadata,
    ReplayHeader ReplayHeader,
    ReplayVersion ReplayVersion,
    UEVersion UEVersion);
