namespace Replay.Models.Replay;

public sealed class ReplayChunkInfo
{
    public ReplayChunkType ChunkType { get; init; } = ReplayChunkType.Unknown;
    public int SizeInBytes { get; init; }
    public long TypeOffset { get; init; }
    public long DataOffset { get; init; }
}