using Replay.Models.Unreal;

namespace Replay.Models.Events;

public sealed record ActorSpawned(
    float TimeSeconds,
    int PacketId,
    uint ActorNetGuid,
    uint ChannelIndex,
    bool IsDynamic,
    string? ActorPath,
    uint ArchetypeNetGuid,
    string? ArchetypePath,
    string? ReplicationClassPath,
    uint LevelNetGuid,
    FVector? Location,
    FRotator? Rotation,
    FVector? Scale,
    FVector? Velocity)
    : ReplayEvent(TimeSeconds, PacketId);