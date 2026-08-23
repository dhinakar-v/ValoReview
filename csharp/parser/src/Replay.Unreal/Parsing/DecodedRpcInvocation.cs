using Replay.Models.Descriptors;
using Replay.Models.Events;

namespace Replay.Unreal.Parsing;

public sealed record DecodedRpcInvocation(
    int Handle,
    string Name,
    string FunctionExportPath,
    ExportCategory Categories,
    int PayloadBits,
    int ParsedBits,
    bool WasDecoded,
    object? Payload,
    int DecodedFieldCount,
    IReadOnlyList<DecodedReplayField> DiagnosticFields);