namespace Replay.Models.Replay;

public sealed class ReplayDataChunkInfo
{
    public int ChunkIndex { get; init; } = ReplayInfo.NoChunkIndex;
    public uint Time1 { get; init; }
    public uint Time2 { get; init; }
    public int SizeInBytes { get; init; }
    public int MemorySizeInBytes { get; init; }
    public long ReplayDataOffset { get; init; }
    public long StreamOffset { get; init; }
}