namespace Replay.Valorant.Descriptors;

public sealed record ValorantRawPayload(
    string TypeName,
    int BitCount,
    ReadOnlyMemory<byte> Data = default)
{
    public override string ToString() => $"{TypeName}({BitCount} bits)";
}
