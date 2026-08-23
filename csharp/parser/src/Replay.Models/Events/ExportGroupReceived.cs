using Replay.Models.Descriptors;

namespace Replay.Models.Events;

public sealed record ExportGroupReceived(
    float TimeSeconds,
    int PacketId,
    uint ActorNetGuid,
    uint ObjectNetGuid,
    uint ChannelIndex,
    bool IsActor,
    bool IsDeleted,
    byte DeleteFlags,
    string? ExportGroupPath,
    ExportGroupKind Kind,
    ExportCategory Categories,
    uint ClassNetGuid,
    uint OuterNetGuid,
    string? ObjectPath,
    string? ClassPath,
    string? OuterPath,
    int PayloadBits,
    int ParsedBits,
    bool WasDecoded,
    object? Payload,
    int DecodedFieldCount,
    IReadOnlyList<DecodedReplayField> DiagnosticFields)
    : ReplayEvent(TimeSeconds, PacketId)
{
    public IReadOnlyList<DecodedReplayField> Fields => DiagnosticFields;
}
