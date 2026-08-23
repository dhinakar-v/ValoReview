using Replay.Models.Descriptors;

namespace Replay.Models.Events;

public sealed record DecodedReplayField(
    int Handle,
    string? Name,
    string? ExportName,
    ExportCategory Categories,
    DecodedFieldValue Value);