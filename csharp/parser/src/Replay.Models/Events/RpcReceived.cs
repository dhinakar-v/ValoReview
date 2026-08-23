using Replay.Models.Descriptors;

namespace Replay.Models.Events;

public sealed record RpcReceived(
    float TimeSeconds,
    int PacketId,
    uint ActorNetGuid,
    uint ObjectNetGuid,
    uint ChannelIndex,
    string ClassPath,
    string FunctionName,
    string FunctionExportPath,
    int FunctionHandle,
    ExportCategory Categories,
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
