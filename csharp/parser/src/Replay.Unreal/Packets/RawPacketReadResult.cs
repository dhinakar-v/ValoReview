namespace Replay.Unreal.Packets;

public readonly struct RawPacketReadResult
{
    public int BunchCount { get; init; }
    public bool IsMalformed { get; init; }
    public int PartialErrorCount { get; init; }
}