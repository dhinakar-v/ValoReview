namespace Replay.Unreal.Packets;

internal struct PartialBunchState
{
    public int ChSequence { get; set; }
    public bool Reliable { get; init; }
    public int CumulativePayloadBitCount { get; set; }
    public bool IsComplete { get; set; }
}